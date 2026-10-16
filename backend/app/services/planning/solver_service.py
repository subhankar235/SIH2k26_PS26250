"""Planning orchestration from normalized problem through verification and audit."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.enums import ScheduleStatus, ValidityStatus, VerificationOutcome
from backend.app.core.exceptions import NotFoundError, RequestValidationFailed, SolverInfeasible
from backend.app.db.models.schedule import Schedule
from backend.app.schemas.planning import ScheduleOut, SolveIn
from backend.app.schemas.validity import AssumptionIn, InputRef
from backend.app.services.audit.audit_service import record as audit_record
from backend.app.services.planning.problem_builder import (
    build_problem,
    input_assignment_map,
    problem_hash,
)
from backend.app.services.validity.assumption_tracker import register_decision
from backend.app.services.validity.status import transition
from backend.app.services.verification.verification_service import run_checks
from optimisation.cpsat.solver import solve
from optimisation.models.problem import Problem


def _plain_problem(problem: Problem) -> dict[str, Any]:
    """Serialize optimizer input into JSON-friendly verifier provenance."""
    return asdict(problem)


def _to_schedule_out(schedule: Schedule) -> ScheduleOut:
    """Validate an ORM schedule row against its public response schema."""
    return ScheduleOut.model_validate(schedule)


def solve_and_verify(db: Session, req: SolveIn, actor: str) -> Schedule:
    """Solve, independently verify, persist, audit, and validity-register a schedule.

    Args:
        db: Active synchronous database session; commit remains owned by its caller.
        req: Validated task/resource problem, solver controls, and deterministic seed.
        actor: Authenticated user responsible for the solve request.

    Returns:
        Persisted schedule with final verification status.

    Raises:
        RequestValidationFailed: If actor or problem configuration is invalid.
        SolverInfeasible: If CP-SAT does not find a feasible schedule.
        ConflictError: If a referenced input or decision version changes during solving.
        SQLAlchemyError: If schedule, decision, or audit state cannot be persisted.
    """
    actor_id = actor.strip()
    if not actor_id:
        raise RequestValidationFailed("A schedule solve requires an actor")
    try:
        problem = build_problem(db, req.problem, forecast_id=req.problem.forecast_id)
        fingerprint = problem_hash(problem)
    except RequestValidationFailed:
        raise
    except (TypeError, ValueError) as error:
        raise RequestValidationFailed(
            "Planning problem is invalid", {"reason": str(error)}
        ) from error

    try:
        solution = solve(problem, req.time_limit_s, req.seed)
    except (TypeError, ValueError) as error:
        raise RequestValidationFailed(
            "Solver configuration is invalid", {"reason": str(error)}
        ) from error
    if solution.status not in {"OPTIMAL", "FEASIBLE"}:
        raise SolverInfeasible(
            "CP-SAT could not find a feasible schedule",
            {"status": solution.status, "solver_meta": solution.metadata},
        )

    if req.use_alns:
        from optimisation.alns.runner import improve

        try:
            improved = improve(
                problem,
                solution,
                iterations=max(1, min(20, len(problem.tasks) * 2)),
                time_limit_s=req.time_limit_s,
                seed=req.seed,
            )
        except (TypeError, ValueError) as error:
            raise SolverInfeasible("ALNS improvement failed", {"reason": str(error)}) from error
        if improved.status in {"OPTIMAL", "FEASIBLE"}:
            solution = improved

    previous = db.scalar(
        select(Schedule)
        .where(Schedule.problem_hash == fingerprint)
        .order_by(Schedule.version.desc(), Schedule.created_at.desc(), Schedule.id)
        .limit(1)
    )
    version = previous.version + 1 if previous is not None else 1
    schedule = Schedule(
        version=version,
        parent_schedule_id=previous.id if previous is not None else None,
        assignments=[asdict(assignment) for assignment in solution.assignments],
        objectives=solution.objectives,
        solver_meta={
            "solver": "ortools_cp_sat",
            "solver_status": solution.status,
            "solver_wall_time_s": solution.wall_time_s,
            "solver_seed": req.seed,
            "solver_time_limit_s": req.time_limit_s,
            "alns_requested": req.use_alns,
            "problem": _plain_problem(problem),
            "input_versions": problem.input_versions,
            "input_assignment_map": input_assignment_map(req.problem, problem),
            "source_problem": req.problem.model_dump(mode="json"),
            "forecast_meta": problem.forecast_meta,
            **solution.metadata,
        },
        status=ScheduleStatus.DRAFT.value,
        problem_hash=fingerprint,
    )
    db.add(schedule)
    db.flush()
    audit_record(
        db,
        "schedule",
        schedule.id,
        "created",
        None,
        {
            "version": schedule.version,
            "status": schedule.status,
            "problem_hash": schedule.problem_hash,
            "assignment_count": len(schedule.assignments),
        },
        actor_id,
    )

    verification = run_checks(db, "schedule", schedule.id, actor_id)
    final_status = {
        VerificationOutcome.VERIFIED: ScheduleStatus.VERIFIED,
        VerificationOutcome.INVALID: ScheduleStatus.INVALID,
        VerificationOutcome.UNCERTAIN: ScheduleStatus.UNCERTAIN,
    }[VerificationOutcome(verification.outcome)]
    old_schedule_version = schedule.version
    schedule.status = final_status.value
    schedule.version += 1
    db.flush()
    audit_record(
        db,
        "schedule",
        schedule.id,
        "verification_status_changed",
        {"status": ScheduleStatus.DRAFT.value, "version": old_schedule_version},
        {
            "status": final_status.value,
            "version": schedule.version,
            "verification_result_id": str(verification.id),
        },
        actor_id,
    )

    inputs = [
        InputRef(
            input_type=item["input_type"],
            input_id=UUID(item["input_id"]),
            input_version=int(item["input_version"]),
        )
        for item in problem.input_versions
    ]
    assumptions = [
        AssumptionIn(
            description=f"Planning policy applies: {policy['name']}",
            parameters=policy["params"],
        )
        for policy in _plain_problem(problem)["policies"]
    ]
    decision = register_decision(db, "schedule", schedule.id, inputs, assumptions)
    outcome = VerificationOutcome(verification.outcome)
    if outcome in {VerificationOutcome.VERIFIED, VerificationOutcome.INVALID}:
        transition(
            db,
            decision,
            ValidityStatus.STALE,
            "New schedule is awaiting its persisted verification outcome",
            actor_id,
        )
        transition(
            db,
            decision,
            (
                ValidityStatus.VERIFIED
                if outcome == VerificationOutcome.VERIFIED
                else ValidityStatus.INVALIDATED
            ),
            "Independent schedule verification completed",
            actor_id,
        )
    return schedule


def get_schedule(db: Session, schedule_id: UUID) -> ScheduleOut:
    """Return a persisted schedule by UUID.

    Args:
        db: Active synchronous database session.
        schedule_id: UUID of the requested schedule.

    Returns:
        Public schedule response.

    Raises:
        NotFoundError: If the schedule does not exist.
    """
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise NotFoundError("Schedule not found", {"id": str(schedule_id)})
    return _to_schedule_out(schedule)
