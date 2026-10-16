"""Tests for problem normalization, invalid input filtering, and Pareto comparison."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core.enums import ScheduleStatus
from backend.app.core.exceptions import ConflictError
from backend.app.db.base import Base
from backend.app.db.models import Forecast, RawEvent, Record, Schedule, Source
from backend.app.schemas.planning import ProblemIn
from backend.app.services.planning.comparator import compare
from backend.app.services.planning.problem_builder import build_problem, problem_hash
from optimisation.alns.runner import improve
from optimisation.cpsat.solver import solve


def _problem_request(**overrides: object) -> ProblemIn:
    """Return a small normalized synthetic scheduling request."""
    values: dict[str, object] = {
        "tasks": [
            {"id": "repair-a", "duration": 2, "resource_type": "crew", "earliest": 0, "latest": 8},
            {"id": "repair-b", "duration": 1, "resource_type": "crew", "earliest": 0, "latest": 8},
        ],
        "resources": [
            {
                "id": "crew-a",
                "type": "crew",
                "capacity": 1,
                "available": [[0, 10]],
                "cost_per_unit": 2.0,
            }
        ],
        "windows": {"horizon": 10},
        "precedence": [],
        "policies": [],
        "objectives": {"makespan": 1.0},
    }
    values.update(overrides)
    return ProblemIn.model_validate(values)


def test_problem_builder_hashes_canonical_inputs_and_captures_versions() -> None:
    """Normalize task/resource problem data and exact record/forecast input versions."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(engine) as db:
        source = Source(name="planning-source", source_type="resource", reliability_prior=0.8)
        db.add(source)
        db.flush()
        raw = RawEvent(
            source_id=source.id,
            source_event_id="planning-record-event",
            payload={"entity_id": "resource:planning", "capacity_mw": 3.0},
            event_time=now,
            ingest_time=now,
        )
        db.add(raw)
        db.flush()
        record = Record(
            entity_id="resource:planning",
            source_type="resource",
            normalised_payload={"entity_id": "resource:planning", "capacity_mw": 3.0},
            source_id=source.id,
            raw_event_id=raw.id,
            event_time=now,
            ingest_time=now,
            version=3,
        )
        db.add(record)
        forecast = Forecast(
            target="resource:planning.load",
            horizon=2,
            points=[
                {"t": "2026-01-01T01:00:00Z", "mean": 10.0, "lower": 8.0, "upper": 12.0}
            ],
            calibration_meta={"target_scale": 10.0},
            input_versions={str(record.id): 3},
            high_uncertainty=False,
            version=4,
        )
        db.add(forecast)
        db.flush()

        request = _problem_request(
            tasks=[
                {
                    "id": "repair-a",
                    "duration": 3,
                    "resource_type": "crew",
                    "record_id": str(record.id),
                }
            ],
            forecast_id=forecast.id,
        )
        problem = build_problem(db, request)

        assert problem.tasks[0].duration == 5
        assert problem.input_versions == [
            {"input_type": "forecast", "input_id": str(forecast.id), "input_version": 4},
            {"input_type": "record", "input_id": str(record.id), "input_version": 3},
        ]
        assert problem.forecast_meta["duration_buffer_fraction"] == 0.4
        assert len(problem_hash(problem)) == 64
        assert problem_hash(problem) == problem_hash(build_problem(db, request))
    engine.dispose()


def test_problem_builder_excludes_open_invalid_records_unless_allowed() -> None:
    """Remove flagged records and their tasks unless the request opts in explicitly."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as db:
        source = Source(name="invalid-source", source_type="resource", reliability_prior=0.5)
        db.add(source)
        db.flush()
        raw = RawEvent(
            source_id=source.id,
            source_event_id="invalid-record-event",
            payload={"entity_id": "resource:invalid"},
            event_time=now,
            ingest_time=now,
        )
        db.add(raw)
        db.flush()
        invalid = Record(
            entity_id="resource:invalid",
            source_type="resource",
            normalised_payload={"entity_id": "resource:invalid"},
            source_id=source.id,
            raw_event_id=raw.id,
            event_time=now,
            ingest_time=now,
            flags=["invalid"],
        )
        db.add(invalid)
        db.flush()

        request = _problem_request(
            tasks=[
                {
                    "id": "bad-task",
                    "duration": 1,
                    "resource_type": "crew",
                    "record_id": str(invalid.id),
                },
                {"id": "good-task", "duration": 1, "resource_type": "crew"},
            ]
        )
        filtered = build_problem(db, request)
        assert [task.id for task in filtered.tasks] == ["good-task"]
        assert all(item["input_id"] != str(invalid.id) for item in filtered.input_versions)

        allowed_request = _problem_request(
            tasks=request.tasks,
            resources=request.resources,
            windows=request.windows,
            objectives=request.objectives,
            policies=[{"name": "allow_invalid_records", "enabled": True}],
        )
        allowed = build_problem(db, allowed_request)
        assert {task.id for task in allowed.tasks} == {"bad-task", "good-task"}
    engine.dispose()


def test_problem_builder_buffers_before_inferring_horizon_and_hashes_policy_order() -> None:
    """Include forecast buffers in inferred horizons and canonicalize policy ordering."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        forecast = Forecast(
            target="resource:planning.load",
            horizon=1,
            points=[{"t": "2026-01-01T01:00:00Z", "mean": 10, "lower": 5, "upper": 15}],
            calibration_meta={"target_scale": 10},
            input_versions={},
            high_uncertainty=True,
            version=1,
        )
        db.add(forecast)
        db.flush()

        request = _problem_request(
            tasks=[{"id": "buffered", "duration": 4, "resource_type": "crew"}],
            resources=[{"id": "crew-a", "type": "crew"}],
            windows={},
            policies=[
                {"name": "beta", "params": {"value": 2}},
                {"name": "alpha", "params": {"value": 1}},
            ],
            forecast_id=forecast.id,
        )
        first = build_problem(db, request)
        reordered = build_problem(
            db,
            _problem_request(
                tasks=request.tasks,
                resources=request.resources,
                windows=request.windows,
                policies=list(reversed(request.policies)),
                forecast_id=forecast.id,
            ),
        )

        assert first.tasks[0].duration == 8
        assert first.horizon == 8
        assert first.tasks[0].latest == 0
        assert problem_hash(first) == problem_hash(reordered)
    engine.dispose()


def test_problem_builder_rejects_explicitly_allowed_stale_records() -> None:
    """Do not use a stale record even when the request opts in to invalid records."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as db:
        source = Source(name="stale-planning-source", source_type="resource", reliability_prior=0.8)
        db.add(source)
        db.flush()
        old_event = RawEvent(
            source_id=source.id,
            source_event_id="stale-planning-old",
            payload={"entity_id": "resource:stale"},
            event_time=now,
            ingest_time=now,
        )
        new_event = RawEvent(
            source_id=source.id,
            source_event_id="stale-planning-new",
            payload={"entity_id": "resource:stale"},
            event_time=now,
            ingest_time=now,
        )
        db.add_all([old_event, new_event])
        db.flush()
        old_record = Record(
            entity_id="resource:stale",
            source_type="resource",
            normalised_payload={"entity_id": "resource:stale"},
            source_id=source.id,
            raw_event_id=old_event.id,
            event_time=now,
            ingest_time=now,
            version=1,
        )
        new_record = Record(
            entity_id="resource:stale",
            source_type="resource",
            normalised_payload={"entity_id": "resource:stale"},
            source_id=source.id,
            raw_event_id=new_event.id,
            event_time=now,
            ingest_time=now,
            version=2,
        )
        db.add_all([old_record, new_record])
        db.flush()
        old_record.superseded_by = new_record.id
        db.flush()

        request = _problem_request(
            tasks=[
                {
                    "id": "stale-task",
                    "duration": 1,
                    "resource_type": "crew",
                    "record_id": str(old_record.id),
                }
            ],
            policies=[{"name": "allow_invalid_records", "enabled": True}],
        )
        with pytest.raises(ConflictError, match="not the latest version"):
            build_problem(db, request)
    engine.dispose()


def test_comparator_computes_minimization_pareto_frontier() -> None:
    """Mark dominated schedules and preserve tied nondominated alternatives."""
    schedules = [
        Schedule(
            id=uuid4(),
            version=1,
            created_at=datetime.now(UTC),
            assignments=[],
            objectives={"makespan": 5.0, "cost": 10.0},
            solver_meta={},
            status=ScheduleStatus.VERIFIED.value,
            problem_hash="problem-a",
        ),
        Schedule(
            id=uuid4(),
            version=1,
            created_at=datetime.now(UTC),
            assignments=[],
            objectives={"makespan": 6.0, "cost": 12.0},
            solver_meta={},
            status=ScheduleStatus.VERIFIED.value,
            problem_hash="problem-a",
        ),
        Schedule(
            id=uuid4(),
            version=1,
            created_at=datetime.now(UTC),
            assignments=[],
            objectives={"makespan": 4.0, "cost": 13.0},
            solver_meta={},
            status=ScheduleStatus.VERIFIED.value,
            problem_hash="problem-a",
        ),
    ]

    result = compare(schedules)
    pareto_by_id = {item.schedule.id: item.pareto_optimal for item in result.alternatives}

    assert result.objective_names == ["cost", "makespan"]
    assert pareto_by_id[schedules[0].id] is True
    assert pareto_by_id[schedules[1].id] is False
    assert pareto_by_id[schedules[2].id] is True


def test_cpsat_solver_respects_precedence_windows_and_resource_capacity() -> None:
    """Find a feasible deterministic solution that satisfies the normalized problem."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        problem = build_problem(
            db,
            _problem_request(
                precedence=[{"before": "repair-a", "after": "repair-b", "min_gap": 1}]
            ),
        )
        first = solve(problem, time_limit_s=2, seed=13)
        repeated = solve(problem, time_limit_s=2, seed=13)

        assert first.status in {"OPTIMAL", "FEASIBLE"}
        assert first.assignments == repeated.assignments
        assignments = {item.task_id: item for item in first.assignments}
        assert assignments["repair-a"].end + 1 <= assignments["repair-b"].start
        assert all(0 <= item.start < item.end <= problem.horizon for item in first.assignments)
    engine.dispose()


def test_cpsat_reports_infeasibility_and_alns_never_worsens_incumbent() -> None:
    """Represent infeasible problems explicitly and preserve a feasible ALNS incumbent."""
    infeasible = ProblemIn(
        tasks=[{"id": "task", "duration": 2, "resource_type": "missing", "latest": 1}],
        resources=[{"id": "resource", "type": "other", "capacity": 1}],
        windows={"horizon": 2},
        objectives={"makespan": 1.0},
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        problem = build_problem(db, infeasible)
        result = solve(problem, time_limit_s=1, seed=2)
        assert result.status == "INFEASIBLE"

        feasible = build_problem(db, _problem_request())
        incumbent = solve(feasible, time_limit_s=1, seed=2)
        improved = improve(feasible, incumbent, iterations=2, time_limit_s=2, seed=2)
        assert improved.status in {"OPTIMAL", "FEASIBLE"}
        assert improved.objectives["makespan"] <= incumbent.objectives["makespan"]
    engine.dispose()
