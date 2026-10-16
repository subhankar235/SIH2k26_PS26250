"""Warm-start replanning, independent verification, persistence, and audit."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any
from uuid import UUID

import networkx as nx  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.enums import ScheduleStatus, ValidityStatus, VerificationOutcome
from backend.app.core.exceptions import (
    ConflictError,
    NotFoundError,
    RequestValidationFailed,
    SolverInfeasible,
)
from backend.app.db.models.decision import Decision
from backend.app.db.models.forecast import Forecast
from backend.app.db.models.record import Record
from backend.app.db.models.schedule import Schedule
from backend.app.schemas.planning import ProblemIn, ScheduleOut
from backend.app.schemas.replanning import ReplanOut
from backend.app.schemas.validity import AssumptionIn, ChangeEvent, InputRef
from backend.app.services.audit.audit_service import record as audit_record
from backend.app.services.planning.problem_builder import (
    build_problem,
    input_assignment_map,
    problem_hash,
)
from backend.app.services.replanning.impact_analysis import ImpactSet, impacted_assignments
from backend.app.services.replanning.schedule_diff import diff as schedule_diff
from backend.app.services.validity.assumption_tracker import register_decision
from backend.app.services.validity.dependency_graph import build as build_dependency_graph
from backend.app.services.validity.input_versions import current_input_version, input_lineage_ids
from backend.app.services.validity.reverifier import reverify
from backend.app.services.validity.status import transition
from backend.app.services.verification.constraint_checker import (
    ProblemData,
    ScheduleData,
    check_all,
)
from backend.app.services.verification.verification_service import run_checks
from optimisation.cpsat.solver import solve
from optimisation.models.problem import Policy, Precedence, Problem, Resource, Task
from optimisation.models.solution import Assignment as SolverAssignment
from optimisation.models.solution import Solution

_RECORD_TYPES = {"record", "resource", "crew", "availability", "weather", "constraint"}


def _same_input_type(left: str, right: str) -> bool:
    """Compare generic and source-specific aliases for versioned record inputs."""
    return left == right or (
        left in _RECORD_TYPES and right in _RECORD_TYPES and "record" in {left, right}
    )


def _load_problem(snapshot: object) -> Problem:
    """Rehydrate the normalized optimizer input stored with a schedule."""
    if not isinstance(snapshot, dict):
        raise RequestValidationFailed("Schedule lacks its normalized problem snapshot")
    try:
        return Problem(
            tasks=[Task(**item) for item in snapshot["tasks"]],
            resources=[
                Resource(
                    id=item["id"],
                    type=item["type"],
                    capacity=item["capacity"],
                    available=[tuple(window) for window in item["available"]],
                    cost_per_unit=item.get("cost_per_unit", 0.0),
                )
                for item in snapshot["resources"]
            ],
            precedence=[Precedence(**item) for item in snapshot.get("precedence", [])],
            policies=[Policy(**item) for item in snapshot.get("policies", [])],
            horizon=int(snapshot["horizon"]),
            objectives=dict(snapshot.get("objectives", {})),
            input_versions=list(snapshot.get("input_versions", [])),
            forecast_meta=dict(snapshot.get("forecast_meta", {})),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RequestValidationFailed(
            "Schedule problem snapshot is malformed", {"reason": str(error)}
        ) from error


def _current_version_id(
    db: Session,
    input_type: str,
    input_id: UUID,
    lineage_ids: set[UUID],
    version: int,
) -> UUID:
    """Resolve the persisted row id representing the current version of an input."""
    if input_type in _RECORD_TYPES:
        candidates = list(
            db.scalars(
                select(Record)
                .where(Record.id.in_(lineage_ids), Record.version == version)
                .order_by(Record.id)
            ).all()
        )
        current = [item for item in candidates if item.superseded_by is None]
        if len(current) == 1:
            return current[0].id
    elif input_type == "forecast":
        requested = db.get(Forecast, input_id)
        if requested is not None:
            current = db.scalar(
                select(Forecast)
                .where(Forecast.target == requested.target, Forecast.version == version)
                .order_by(Forecast.created_at.desc(), Forecast.id)
                .limit(1)
            )
            if current is not None:
                return UUID(str(current.id))
    elif input_type == "schedule":
        current = db.scalar(
            select(Schedule)
            .where(Schedule.id.in_(lineage_ids), Schedule.version == version)
            .order_by(Schedule.created_at.desc(), Schedule.id)
            .limit(1)
        )
        if current is not None:
            return UUID(str(current.id))
    if input_id in lineage_ids:
        return input_id
    raise ConflictError(
        "Could not resolve the current input row for replanning",
        {"input_type": input_type, "input_id": str(input_id), "version": version},
    )


def _apply_changes(
    db: Session,
    problem: Problem,
    changes: list[ChangeEvent],
) -> tuple[Problem, list[ChangeEvent], dict[str, str]]:
    """Validate changes against current rows and update input-version provenance."""
    if not changes:
        raise RequestValidationFailed("At least one changed input is required")
    refs = list(problem.input_versions)
    updated_refs = {(item["input_type"], UUID(str(item["input_id"]))): dict(item) for item in refs}
    normalized_events: list[ChangeEvent] = []
    id_remap: dict[str, str] = {}
    seen: set[tuple[str, UUID]] = set()
    seen_lineage_ids: set[UUID] = set()

    for event in changes:
        if event.old_version is not None and event.new_version <= event.old_version:
            raise RequestValidationFailed(
                "Changed input version must increase",
                {"input_id": str(event.input_id), "old_version": event.old_version},
            )
        current_version = current_input_version(db, event.input_type, event.input_id)
        if current_version is None:
            raise RequestValidationFailed(
                "Changed input does not identify a supported persisted input",
                {"input_type": event.input_type, "input_id": str(event.input_id)},
            )
        if current_version != event.new_version:
            raise ConflictError(
                "Changed input version does not match the current persisted version",
                {
                    "input_type": event.input_type,
                    "input_id": str(event.input_id),
                    "provided_version": event.new_version,
                    "current_version": current_version,
                },
            )
        lineage = input_lineage_ids(db, event.input_type, event.input_id)
        if not lineage:
            lineage = {event.input_id}
        if seen_lineage_ids & lineage:
            raise RequestValidationFailed(
                "A logical input lineage may only be changed once per replan",
                {"input_type": event.input_type, "input_id": str(event.input_id)},
            )
        seen_lineage_ids.update(lineage)
        matching = [
            (key, ref)
            for key, ref in updated_refs.items()
            if key[1] in lineage and _same_input_type(key[0], event.input_type)
        ]
        if not matching:
            raise RequestValidationFailed(
                "Changed input is not a dependency of this schedule",
                {"input_type": event.input_type, "input_id": str(event.input_id)},
            )
        row_id = _current_version_id(
            db, event.input_type, event.input_id, lineage, event.new_version
        )
        for (stored_type, stored_id), old_ref in matching:
            identity = (stored_type, stored_id)
            if identity in seen:
                raise RequestValidationFailed(
                    "A schedule input may only be changed once per replan",
                    {"input_type": stored_type, "input_id": str(stored_id)},
                )
            seen.add(identity)
            old_version = int(old_ref["input_version"])
            if event.old_version is not None and event.old_version != old_version:
                raise ConflictError(
                    "Changed input old_version does not match the schedule dependency",
                    {
                        "input_id": str(stored_id),
                        "schedule_version": old_version,
                        "provided_old_version": event.old_version,
                    },
                )
            if event.new_version <= old_version:
                raise RequestValidationFailed(
                    "Changed input version must be newer than the schedule dependency",
                    {"input_id": str(stored_id), "old_version": old_version},
                )
            updated_refs.pop(identity)
            new_identity = (stored_type, row_id)
            updated_refs[new_identity] = {
                "input_type": stored_type,
                "input_id": str(row_id),
                "input_version": event.new_version,
            }
            id_remap[str(stored_id)] = str(row_id)
            normalized_events.append(
                ChangeEvent(
                    input_type=stored_type,
                    input_id=stored_id,
                    old_version=old_version,
                    new_version=event.new_version,
                    changed_at=event.changed_at,
                )
            )

    updated = replace(
        problem,
        input_versions=[
            updated_refs[key]
            for key in sorted(updated_refs, key=lambda item: (item[0], str(item[1])))
        ],
    )
    return updated, normalized_events, id_remap


def _updated_assignment_map(
    schedule: Schedule, id_remap: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """Carry task/resource provenance forward to current input ids."""
    old = schedule.solver_meta.get("input_assignment_map", {})
    if not isinstance(old, dict):
        return {}
    updated: dict[str, dict[str, Any]] = {}
    for input_id, raw in old.items():
        if not isinstance(raw, dict):
            continue
        key = id_remap.get(str(input_id), str(input_id))
        target = updated.setdefault(key, {"task_ids": [], "resource_ids": [], "global": False})
        for field in ("task_ids", "resource_ids"):
            values = raw.get(field, [])
            if isinstance(values, list):
                target[field].extend(item for item in values if item not in target[field])
        target["global"] = target["global"] or raw.get("global") is True
    for value in updated.values():
        value["task_ids"].sort()
        value["resource_ids"].sort()
    return updated


def _solver_assignments(schedule: Schedule) -> list[SolverAssignment]:
    """Parse prior persisted assignments for a seeded solver hint."""
    try:
        return [SolverAssignment(**item) for item in schedule.assignments]
    except (TypeError, ValueError) as error:
        raise RequestValidationFailed(
            "Prior schedule assignments are malformed", {"schedule_id": str(schedule.id)}
        ) from error


def _independently_feasible(problem: Problem, assignments: list[SolverAssignment]) -> bool:
    """Check candidate assignments before choosing incremental or fallback output."""
    snapshot = asdict(problem)
    violations = check_all(
        ScheduleData([asdict(item) for item in assignments]),
        ProblemData(
            tasks=snapshot["tasks"],
            resources=snapshot["resources"],
            precedence=snapshot["precedence"],
            policies=snapshot["policies"],
            horizon=snapshot["horizon"],
        ),
    )
    return not violations


def _plain_assignment_map(
    schedule: Schedule, id_remap: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """Alias helper kept separate for an explicit serialized solver metadata boundary."""
    return _updated_assignment_map(schedule, id_remap)


def _decision_assumptions(problem: Problem) -> list[AssumptionIn]:
    """Convert planning policies into validity-envelope assumptions."""
    return [
        AssumptionIn(
            description=f"Planning policy applies: {policy.name}",
            parameters=policy.params,
        )
        for policy in problem.policies
        if policy.name != "fixed_assignments"
    ]


def _register_schedule_decision(
    db: Session,
    schedule: Schedule,
    problem: Problem,
    verification_outcome: VerificationOutcome,
    actor: str,
) -> Decision:
    """Register the new schedule's input dependencies and verification status."""
    inputs = [
        InputRef(
            input_type=item["input_type"],
            input_id=UUID(item["input_id"]),
            input_version=int(item["input_version"]),
        )
        for item in problem.input_versions
    ]
    decision = register_decision(
        db, "schedule", schedule.id, inputs, _decision_assumptions(problem)
    )
    if verification_outcome in {VerificationOutcome.VERIFIED, VerificationOutcome.INVALID}:
        transition(
            db,
            decision,
            ValidityStatus.STALE,
            "Replanned schedule is awaiting its persisted verification outcome",
            actor,
        )
        transition(
            db,
            decision,
            (
                ValidityStatus.VERIFIED
                if verification_outcome == VerificationOutcome.VERIFIED
                else ValidityStatus.INVALIDATED
            ),
            "Independent replanning verification completed",
            actor,
        )
    return decision


def _solve_candidate(
    problem: Problem,
    previous: list[SolverAssignment],
    *,
    fixed_assignments: list[dict[str, Any]],
    time_limit_s: int,
    seed: int,
) -> Solution:
    """Run CP-SAT with fixed unaffected work and a full prior-schedule hint."""
    candidate_problem = (
        replace(
            problem,
            policies=[
                *problem.policies,
                Policy("fixed_assignments", {"assignments": fixed_assignments}),
            ],
        )
        if fixed_assignments
        else problem
    )
    hint = Solution(
        assignments=previous,
        objectives={},
        status="FEASIBLE",
        wall_time_s=0.0,
        seed=seed,
    )
    return solve(candidate_problem, time_limit_s=time_limit_s, seed=seed, hint=hint)


def replan(db: Session, schedule_id: UUID, changes: list[ChangeEvent], actor: str) -> ReplanOut:
    """Incrementally recompute a schedule and fall back safely when needed.

    The replacement is independently checked before the old schedule is marked
    superseded. Unverified replacements are retained for review without replacing
    the prior schedule.

    Args:
        db: Active synchronous database session; transaction is caller-owned.
        schedule_id: Schedule to replan.
        changes: Version changes that triggered the replan.
        actor: Authenticated actor requesting the update.

    Returns:
        The new schedule, assignment diff, and whether a full solve was required.

    Raises:
        ConflictError: If a changed input no longer has the provided current version.
        NotFoundError: If the old schedule does not exist.
        RequestValidationFailed: If the snapshot, actor, or changes are invalid.
        SolverInfeasible: If a full solve cannot produce an independently feasible plan.
    """
    actor_id = actor.strip()
    if not actor_id:
        raise RequestValidationFailed("A schedule replan requires an actor")
    old_schedule = db.scalar(
        select(Schedule)
        .where(Schedule.id == schedule_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if old_schedule is None:
        raise NotFoundError("Schedule not found", {"id": str(schedule_id)})
    problem = _load_problem(old_schedule.solver_meta.get("problem"))
    problem, normalized_changes, id_remap = _apply_changes(db, problem, changes)
    source_problem_data = old_schedule.solver_meta.get("source_problem")
    source_problem: ProblemIn | None = None
    if isinstance(source_problem_data, dict):
        refreshed_source = dict(source_problem_data)
        for key in ("tasks", "resources"):
            rows = refreshed_source.get(key, [])
            if isinstance(rows, list):
                refreshed_source[key] = [
                    {
                        **row,
                        **(
                            {"record_id": id_remap[str(row["record_id"])]}
                            if isinstance(row, dict)
                            and row.get("record_id") is not None
                            and str(row["record_id"]) in id_remap
                            else {}
                        ),
                    }
                    for row in rows
                    if isinstance(row, dict)
                ]
        forecast_id = refreshed_source.get("forecast_id")
        if forecast_id is not None and str(forecast_id) in id_remap:
            refreshed_source["forecast_id"] = id_remap[str(forecast_id)]
        try:
            source_problem = ProblemIn.model_validate(refreshed_source)
            problem = build_problem(db, source_problem)
        except (TypeError, ValueError) as error:
            raise RequestValidationFailed(
                "Updated source problem is invalid", {"reason": str(error)}
            ) from error
    graph: nx.DiGraph = build_dependency_graph(db)
    impact: ImpactSet = impacted_assignments(old_schedule, normalized_changes, graph)
    previous_assignments = _solver_assignments(old_schedule)
    previous_task_ids = [item.task_id for item in previous_assignments]
    if len(set(previous_task_ids)) != len(previous_task_ids):
        raise RequestValidationFailed(
            "Prior schedule contains duplicate task assignments",
            {"schedule_id": str(old_schedule.id)},
        )

    solver_meta = old_schedule.solver_meta
    time_limit = int(solver_meta.get("solver_time_limit_s", 30))
    if time_limit < 1:
        time_limit = 30
    seed = int(solver_meta.get("solver_seed", 0))
    current_task_ids = {task.id for task in problem.tasks}
    partial_tasks = (set(impact.task_ids) & current_task_ids) | (
        current_task_ids - set(previous_task_ids)
    )
    fixed = [
        {
            "task_id": item.task_id,
            "resource_id": item.resource_id,
            "start": item.start,
            "end": item.end,
        }
        for item in previous_assignments
        if item.task_id in current_task_ids and item.task_id not in partial_tasks
    ]
    partial_possible = (
        not impact.requires_full_solve
        and bool(fixed)
        and bool(current_task_ids - partial_tasks)
    )
    fallback = not partial_possible
    candidate: Solution | None = None
    half_limit = max(1, time_limit // 2)
    if partial_possible:
        try:
            attempted = _solve_candidate(
                problem,
                previous_assignments,
                fixed_assignments=fixed,
                time_limit_s=half_limit,
                seed=seed,
            )
            if attempted.status in {"OPTIMAL", "FEASIBLE"} and _independently_feasible(
                problem, attempted.assignments
            ):
                candidate = attempted
            else:
                fallback = True
        except (KeyError, TypeError, ValueError, RuntimeError):
            fallback = True

    if candidate is None:
        try:
            candidate = solve(
                problem,
                time_limit_s=max(1, time_limit - half_limit if partial_possible else time_limit),
                seed=seed,
                hint=Solution(
                    assignments=previous_assignments,
                    objectives=old_schedule.objectives,
                    status="FEASIBLE",
                    wall_time_s=0.0,
                    seed=seed,
                ),
            )
        except (TypeError, ValueError, RuntimeError) as error:
            raise SolverInfeasible("Full re-solve failed", {"reason": str(error)}) from error
        if candidate.status not in {"OPTIMAL", "FEASIBLE"}:
            raise SolverInfeasible(
                "Full re-solve could not find a feasible schedule",
                {"status": candidate.status, "solver_meta": candidate.metadata},
            )
        if not _independently_feasible(problem, candidate.assignments):
            raise SolverInfeasible("Full re-solve failed independent feasibility checks")

    assignment_map = (
        input_assignment_map(source_problem, problem)
        if source_problem is not None
        else _plain_assignment_map(old_schedule, id_remap)
    )
    normalized_problem = asdict(problem)
    next_schedule = Schedule(
        version=old_schedule.version + 1,
        parent_schedule_id=old_schedule.id,
        assignments=[asdict(item) for item in candidate.assignments],
        objectives=candidate.objectives,
        solver_meta={
            "solver": "ortools_cp_sat",
            "solver_status": candidate.status,
            "solver_wall_time_s": candidate.wall_time_s,
            "solver_seed": seed,
            "solver_time_limit_s": time_limit,
            "alns_requested": solver_meta.get("alns_requested", False),
            "problem": normalized_problem,
            "input_versions": problem.input_versions,
            "input_assignment_map": assignment_map,
            "source_problem": (
                source_problem.model_dump(mode="json")
                if source_problem is not None
                else source_problem_data
            ),
            "forecast_meta": problem.forecast_meta,
            "replanned_from": str(old_schedule.id),
            "changed_inputs": [event.model_dump(mode="json") for event in normalized_changes],
            "fallback_to_full_solve": fallback,
            **candidate.metadata,
        },
        status=ScheduleStatus.DRAFT.value,
        problem_hash=problem_hash(problem),
    )
    db.add(next_schedule)
    db.flush()
    audit_record(
        db,
        "schedule",
        next_schedule.id,
        "replan_created",
        {"schedule_id": str(old_schedule.id), "version": old_schedule.version},
        {
            "version": next_schedule.version,
            "status": next_schedule.status,
            "fallback_to_full_solve": fallback,
            "changed_input_count": len(normalized_changes),
        },
        actor_id,
    )

    verification = run_checks(db, "schedule", next_schedule.id, actor_id)
    outcome = VerificationOutcome(verification.outcome)
    next_schedule.status = {
        VerificationOutcome.VERIFIED: ScheduleStatus.VERIFIED,
        VerificationOutcome.INVALID: ScheduleStatus.INVALID,
        VerificationOutcome.UNCERTAIN: ScheduleStatus.UNCERTAIN,
    }[outcome].value
    draft_version = next_schedule.version
    next_schedule.version += 1
    db.flush()
    audit_record(
        db,
        "schedule",
        next_schedule.id,
        "verification_status_changed",
        {"status": ScheduleStatus.DRAFT.value, "version": draft_version},
        {
            "status": next_schedule.status,
            "version": next_schedule.version,
            "verification_result_id": str(verification.id),
        },
        actor_id,
    )

    reverify(db, changes)
    _register_schedule_decision(db, next_schedule, problem, outcome, actor_id)
    if outcome == VerificationOutcome.VERIFIED:
        previous_status = old_schedule.status
        previous_version = old_schedule.version
        old_schedule.status = ScheduleStatus.SUPERSEDED.value
        old_schedule.version += 1
        db.flush()
        audit_record(
            db,
            "schedule",
            old_schedule.id,
            "superseded",
            {"status": previous_status, "version": previous_version},
            {
                "status": old_schedule.status,
                "version": old_schedule.version,
                "replacement_schedule_id": str(next_schedule.id),
            },
            actor_id,
        )
    audit_record(
        db,
        "schedule",
        next_schedule.id,
        "replan_completed",
        None,
        {
            "parent_schedule_id": str(old_schedule.id),
            "status": next_schedule.status,
            "fallback_to_full_solve": fallback,
        },
        actor_id,
    )
    return ReplanOut(
        schedule=ScheduleOut.model_validate(next_schedule),
        diff=schedule_diff(old_schedule, next_schedule),
        fallback_to_full_solve=fallback,
    )
