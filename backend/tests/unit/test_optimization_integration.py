"""Focused tests for solver inputs, results, and backend persistence."""

from __future__ import annotations

import subprocess
import sys

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.core.enums import ScheduleStatus
from backend.app.core.exceptions import SolverOutcomeError
from backend.app.db.base import Base
from backend.app.db.models.approval import VerificationResult
from backend.app.db.models.schedule import Schedule
from backend.app.schemas.planning import ProblemIn, SolveIn
from backend.app.services.optimization.cpsat.solver import solve
from backend.app.services.optimization.incremental.partial_resolve import partial_resolve
from backend.app.services.optimization.integration.input_adapter import to_problem
from backend.app.services.optimization.integration.output_adapter import to_schedule_values
from backend.app.services.optimization.models.problem import ProblemValidationError
from backend.app.services.optimization.models.solution import Assignment, Solution
from backend.app.services.planning.solver_service import solve_and_verify
from backend.app.services.replanning.schedule_diff import diff_schedules
from backend.app.services.verification.constraint_checker import check_schedule

PROBLEM = {
    "tasks": [
        {
            "task_id": "task-a",
            "duration": 2,
            "required_resource_type": "crew",
            "earliest_start": 0,
            "latest_end": 8,
            "priority": 1,
        }
    ],
    "resources": [
        {
            "resource_id": "crew-1",
            "resource_type": "crew",
            "capacity": 1,
            "availability": [{"start": 0, "end": 8}],
        }
    ],
    "windows": {"start": 0, "end": 8},
    "precedence": [],
    "policies": [],
    "objectives": {"makespan": 1},
}


@pytest.fixture
def db_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_valid_snapshot_builds_and_solves_integer_tick_problem() -> None:
    problem = to_problem(PROBLEM)
    assert problem.tasks[0].task_id == "task-a"
    assert problem.resources[0].availability == ((0, 8),)
    solution = solve(problem, time_limit_s=2, seed=7)
    assert solution.status == "OPTIMAL"
    assert solution.assignments[0].end - solution.assignments[0].start == 2
    assert solution.assignments[0].resource_id == "crew-1"


def test_missing_task_data_has_clear_validation_error() -> None:
    invalid = {**PROBLEM, "tasks": [{**PROBLEM["tasks"][0]}]}
    invalid["tasks"][0].pop("duration")
    with pytest.raises(ProblemValidationError, match="tasks\\[0\\]\\.duration is required"):
        to_problem(invalid)


def test_unknown_or_ineligible_resource_is_rejected() -> None:
    invalid = {**PROBLEM, "resources": [{**PROBLEM["resources"][0], "resource_type": "vehicle"}]}
    with pytest.raises(ProblemValidationError, match="no eligible resource"):
        to_problem(invalid)


def test_timestamp_and_non_integer_times_are_not_mixed_with_ticks() -> None:
    invalid = {**PROBLEM, "windows": {"start": 0, "end": 8.0}}
    with pytest.raises(ProblemValidationError, match="windows.end must be an integer"):
        to_problem(invalid)
    converted = to_problem(PROBLEM)
    assert converted.horizon_start == 0
    assert converted.horizon_end == 8


def test_output_adapter_preserves_solver_status_and_metadata() -> None:
    problem = to_problem(PROBLEM)
    assignment = Assignment("task-a", "crew-1", 1, 3)
    feasible = Solution("FEASIBLE", (assignment,), {"makespan": 3.0}, 0.2, 13)
    values = to_schedule_values(problem, feasible, time_limit_s=5)
    assert values["assignments"] == [
        {"task_id": "task-a", "resource_id": "crew-1", "start": 1, "end": 3}
    ]
    assert values["solver_meta"]["solver_status"] == "FEASIBLE"
    assert values["solver_meta"]["random_seed"] == 13
    assert len(values["problem_hash"]) == 64
    assert values["status"] == ScheduleStatus.DRAFT.value


def test_partial_resolve_handles_changed_availability_and_removed_tasks() -> None:
    previous_problem = to_problem(PROBLEM)
    previous = solve(previous_problem, time_limit_s=2, seed=7)
    availability_changed = {
        **PROBLEM,
        "resources": [
            {
                **PROBLEM["resources"][0],
                "availability": [{"start": 4, "end": 8}],
            }
        ],
    }
    updated = to_problem(availability_changed)
    replanned = partial_resolve(updated, previous, set(), time_limit_s=2, seed=7)
    assert replanned.status == "OPTIMAL"
    assert replanned.assignments[0].start >= 4

    removed_task_problem = {
        **PROBLEM,
        "tasks": [
            {
                **PROBLEM["tasks"][0],
                "task_id": "task-b",
            }
        ],
    }
    removed_task = partial_resolve(
        to_problem(removed_task_problem),
        previous,
        {"task-a"},
        time_limit_s=2,
        seed=7,
    )
    assert removed_task.status == "OPTIMAL"
    assert [item.task_id for item in removed_task.assignments] == ["task-b"]


@pytest.mark.parametrize("status", ["INFEASIBLE", "UNKNOWN"])
def test_unsuccessful_solver_status_does_not_create_schedule(
    monkeypatch, db_session, status: str
) -> None:
    result = Solution(status, (), {}, 0.1, 5)
    monkeypatch.setattr(
        "backend.app.services.planning.solver_service.solve", lambda *args, **kwargs: result
    )
    request = SolveIn(problem=ProblemIn.model_validate(PROBLEM), time_limit_s=2, seed=5)
    with pytest.raises(SolverOutcomeError) as error:
        solve_and_verify(db_session, request, "test-actor")
    assert error.value.details == {"solver_status": status, "execution_time_s": 0.1}
    assert db_session.scalar(select(func.count()).select_from(Schedule)) == 0


def test_optimal_solution_is_verified_and_never_auto_approved(db_session) -> None:
    request = SolveIn(problem=ProblemIn.model_validate(PROBLEM), time_limit_s=2, seed=5)
    response = solve_and_verify(db_session, request, "test-actor")
    persisted = db_session.get(Schedule, response.id)
    assert persisted is not None
    assert persisted.status == ScheduleStatus.VERIFIED.value
    assert persisted.solver_meta["solver_status"] == "OPTIMAL"
    assert db_session.scalar(select(func.count()).select_from(VerificationResult)) == 1


def test_feasible_result_stays_distinct_in_persisted_solver_metadata(
    monkeypatch, db_session
) -> None:
    feasible = Solution(
        "FEASIBLE",
        (Assignment("task-a", "crew-1", 1, 3),),
        {"makespan": 3.0},
        0.2,
        5,
    )
    monkeypatch.setattr(
        "backend.app.services.planning.solver_service.solve",
        lambda *args, **kwargs: feasible,
    )
    request = SolveIn(problem=ProblemIn.model_validate(PROBLEM), time_limit_s=2, seed=5)
    response = solve_and_verify(db_session, request, "test-actor")
    persisted = db_session.get(Schedule, response.id)
    assert persisted is not None
    assert persisted.status == ScheduleStatus.VERIFIED.value
    assert persisted.solver_meta["solver_status"] == "FEASIBLE"


def test_independent_verifier_rejects_an_ineligible_candidate() -> None:
    violations = check_schedule(
        PROBLEM,
        [{"task_id": "task-a", "resource_id": "unknown", "start": 0, "end": 2}],
    )
    assert any(violation["rule"] == "resource_reference" for violation in violations)


def test_service_persists_failed_verification_as_invalid(monkeypatch, db_session) -> None:
    invalid = Solution(
        "OPTIMAL",
        (Assignment("task-a", "unknown-resource", 0, 2),),
        {"makespan": 2.0},
        0.1,
        5,
    )
    monkeypatch.setattr(
        "backend.app.services.planning.solver_service.solve",
        lambda *args, **kwargs: invalid,
    )
    request = SolveIn(problem=ProblemIn.model_validate(PROBLEM), time_limit_s=2, seed=5)
    response = solve_and_verify(db_session, request, "test-actor")
    persisted = db_session.get(Schedule, response.id)
    result = db_session.scalar(select(VerificationResult))
    assert persisted is not None
    assert persisted.status == ScheduleStatus.INVALID.value
    assert result is not None and result.outcome == "invalid"
    assert any(item["rule"] == "resource_reference" for item in result.violations)


def test_schedule_diff_classifies_removed_added_and_moved_tasks() -> None:
    result = diff_schedules(
        [
            {"task_id": "kept", "resource_id": "r1", "start": 0, "end": 1},
            {"task_id": "moved", "resource_id": "r1", "start": 1, "end": 2},
            {"task_id": "removed", "resource_id": "r1", "start": 2, "end": 3},
        ],
        [
            {"task_id": "kept", "resource_id": "r1", "start": 0, "end": 1},
            {"task_id": "moved", "resource_id": "r2", "start": 3, "end": 4},
            {"task_id": "added", "resource_id": "r1", "start": 4, "end": 5},
        ],
    )
    assert [item["task_id"] for item in result.added] == ["added"]
    assert [item["task_id"] for item in result.removed] == ["removed"]
    assert [item.task_id for item in result.moved] == ["moved"]
    assert result.unchanged == 1


def test_optimizer_import_does_not_load_fastapi_or_database_session() -> None:
    code = (
        "import sys; "
        "import backend.app.services.optimization.models.problem; "
        "assert 'fastapi' not in sys.modules; "
        "assert 'backend.app.db.session' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
