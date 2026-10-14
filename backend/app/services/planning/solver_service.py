"""Planning orchestration and schedule persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.enums import ScheduleStatus, VerificationOutcome
from backend.app.core.exceptions import NotFoundError, RequestValidationFailed, SolverOutcomeError
from backend.app.db.models.approval import VerificationResult
from backend.app.db.models.schedule import Schedule
from backend.app.schemas.planning import ScheduleOut, SolveIn
from backend.app.services.audit.audit_service import record as audit_record
from backend.app.services.optimization.cpsat.solver import solve
from backend.app.services.optimization.integration.output_adapter import to_schedule_values
from backend.app.services.optimization.models.problem import ProblemValidationError
from backend.app.services.planning.problem_builder import build_problem
from backend.app.services.verification.constraint_checker import check_schedule


def solve_and_verify(db: Session, request: SolveIn, actor: str) -> ScheduleOut:
    """Validate, solve, independently verify, and persist a schedule candidate."""
    if request.use_alns:
        raise RequestValidationFailed("ALNS refinement is not implemented for this workflow")
    try:
        problem = build_problem(db, request.problem)
    except ProblemValidationError as error:
        raise RequestValidationFailed(str(error)) from error
    time_limit = request.time_limit_s
    result = solve(problem, time_limit_s=time_limit, seed=request.seed)
    if result.status in {"INFEASIBLE", "UNKNOWN"}:
        raise SolverOutcomeError(
            f"CP-SAT returned {result.status}; no usable schedule was created",
            {"solver_status": result.status, "execution_time_s": result.wall_time_s},
        )

    values = to_schedule_values(problem, result, time_limit_s=time_limit)
    violations = check_schedule(request.problem.model_dump(mode="json"), values["assignments"])
    values["status"] = ScheduleStatus.INVALID.value if violations else ScheduleStatus.VERIFIED.value
    schedule = Schedule(**values)
    db.add(schedule)
    db.flush()
    verification = VerificationResult(
        target_type="schedule",
        target_id=schedule.id,
        outcome=VerificationOutcome.INVALID.value
        if violations
        else VerificationOutcome.VERIFIED.value,
        violations=violations,
        uncertainty_flags=[],
    )
    db.add(verification)
    db.flush()
    audit_record(
        db,
        "schedule",
        schedule.id,
        "created",
        None,
        {
            "status": schedule.status,
            "solver_status": result.status,
            "verification_result_id": str(verification.id),
            "problem_hash": schedule.problem_hash,
        },
        str(actor),
    )
    return _schedule_out(schedule)


def get_schedule(db: Session, schedule_id: UUID) -> ScheduleOut:
    """Return one persisted schedule."""
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise NotFoundError("Schedule not found", {"schedule_id": str(schedule_id)})
    return _schedule_out(schedule)


def list_schedules(db: Session) -> list[Schedule]:
    """Return persisted schedule candidates in stable identifier order."""
    return list(db.scalars(select(Schedule).order_by(Schedule.id)).all())


def _schedule_out(schedule: Schedule) -> ScheduleOut:
    return ScheduleOut.model_validate(schedule)
