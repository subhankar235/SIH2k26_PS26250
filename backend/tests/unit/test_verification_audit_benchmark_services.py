"""Tests for independent verification, approvals, audit reads, and benchmark reads."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core.enums import ApprovalDecision
from backend.app.core.exceptions import ConflictError, RequestValidationFailed
from backend.app.core.security import Actor
from backend.app.db.base import Base
from backend.app.db.models import (
    AuditEntry,
    ExperimentRun,
    Forecast,
    Issue,
    RawEvent,
    Record,
    Schedule,
    Source,
)
from backend.app.schemas.audit import AuditQuery
from backend.app.services.audit.audit_service import history, query, record
from backend.app.services.benchmarking.results_service import ablations, results
from backend.app.services.verification.approval_router import decide, queue, route
from backend.app.services.verification.consistency_checker import (
    check_evidence_links,
    check_forecast_link,
    check_versions,
)
from backend.app.services.verification.constraint_checker import (
    ProblemData,
    ScheduleData,
    check_all,
)
from backend.app.services.verification.uncertainty_flagger import flags
from backend.app.services.verification.verification_service import get, run_checks


def _db() -> tuple[object, Session]:
    """Create an isolated complete SQLite schema and active session."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def _schedule(
    db: Session,
    *,
    assignments: list[dict[str, object]] | None = None,
    inputs: list[dict[str, object]] | None = None,
    forecast_meta: dict[str, object] | None = None,
    tasks: list[dict[str, object]] | None = None,
    policies: list[dict[str, object]] | None = None,
) -> Schedule:
    """Persist a small schedule with independently verifiable provenance."""
    schedule = Schedule(
        version=1,
        assignments=assignments
        if assignments is not None
        else [{"task_id": "task-a", "resource_id": "crew-a", "start": 0, "end": 2}],
        objectives={"makespan": 2.0},
        solver_meta={
            "problem": {
                "tasks": tasks
                if tasks is not None
                else [
                    {
                        "id": "task-a",
                        "duration": 2,
                        "resource_type": "crew",
                        "earliest": 0,
                        "latest": 4,
                    }
                ],
                "resources": [
                    {"id": "crew-a", "type": "crew", "capacity": 1, "available": [[0, 8]]}
                ],
                "precedence": [],
                "policies": policies or [],
                "horizon": 8,
            },
            "input_versions": inputs or [],
            "forecast_meta": forecast_meta or {},
        },
        status="draft",
        problem_hash="a" * 64,
    )
    db.add(schedule)
    db.flush()
    return schedule


def test_independent_checker_enforces_task_duration_and_policy() -> None:
    """Reject corrupted durations and policies, without requiring solver imports."""
    problem = ProblemData(
        tasks=[{"id": "task", "duration": 3, "resource_type": "crew", "latest": 4}],
        resources=[{"id": "crew", "type": "crew", "capacity": 1, "available": [[0, 8]]}],
        policies=[{"name": "unsupported_policy", "params": {}}],
        horizon=8,
    )
    violations = check_all(
        ScheduleData([{"task_id": "task", "resource_id": "crew", "start": 0, "end": 2}]),
        problem,
    )

    rules = {item.rule for item in violations}
    assert "task_duration" in rules
    assert "unsupported_policy" in rules


def test_consistency_and_uncertainty_cover_forecast_conflict_and_stale_inputs() -> None:
    """Detect stale records, a high-uncertainty forecast, and an open linked conflict."""
    engine, db = _db()
    now = datetime.now(UTC)
    try:
        source = Source(name="verify-source", source_type="resource", reliability_prior=0.8)
        db.add(source)
        db.flush()
        old_event = RawEvent(
            source_id=source.id,
            source_event_id="verify-old",
            payload={"entity_id": "resource:verify"},
            event_time=now,
            ingest_time=now,
        )
        new_event = RawEvent(
            source_id=source.id,
            source_event_id="verify-new",
            payload={"entity_id": "resource:verify"},
            event_time=now,
            ingest_time=now,
        )
        db.add_all([old_event, new_event])
        db.flush()
        old_record = Record(
            entity_id="resource:verify",
            source_type="resource",
            normalised_payload={"entity_id": "resource:verify"},
            source_id=source.id,
            raw_event_id=old_event.id,
            event_time=now,
            ingest_time=now,
            version=1,
        )
        current_record = Record(
            entity_id="resource:verify",
            source_type="resource",
            normalised_payload={"entity_id": "resource:verify"},
            source_id=source.id,
            raw_event_id=new_event.id,
            event_time=now,
            ingest_time=now,
            version=2,
        )
        db.add_all([old_record, current_record])
        db.flush()
        old_record.superseded_by = current_record.id
        forecast = Forecast(
            target="resource:verify.load",
            horizon=1,
            points=[{"t": now.isoformat(), "mean": 10, "lower": 1, "upper": 19}],
            calibration_meta={"target_scale": 10},
            input_versions={},
            high_uncertainty=True,
            version=1,
        )
        db.add(forecast)
        db.flush()
        schedule = _schedule(
            db,
            inputs=[
                {"input_type": "record", "input_id": str(old_record.id), "input_version": 1},
                {"input_type": "forecast", "input_id": str(forecast.id), "input_version": 1},
            ],
            forecast_meta={"forecast_id": str(forecast.id)},
        )
        db.add(
            Issue(
                issue_class="conflict",
                claim_ids=[],
                detected_at=now,
                status="open",
                details={"entity_id": old_record.entity_id},
            )
        )
        db.flush()

        assert {item.rule for item in check_versions(db, schedule)} == {"input_version"}
        assert check_forecast_link(db, schedule) == []
        assert check_evidence_links(db, schedule) == []
        result = {item.code for item in flags(db, schedule, threshold=0.35)}
        assert result >= {"HIGH_FORECAST_UNCERTAINTY", "UNRESOLVED_CONFLICT", "STALE_INPUT"}
    finally:
        db.close()
        engine.dispose()


def test_run_checks_persists_outcome_and_human_approval_state_machine() -> None:
    """Route verified/uncertain results and enforce latest verified approval only."""
    engine, db = _db()
    try:
        schedule = _schedule(db)
        verified = run_checks(db, "schedule", schedule.id, "verifier")
        assert verified.outcome == "verified"
        assert route(db, verified) is not None
        page = queue(db, limit=10, offset=0)
        assert page.total == 1
        assert page.items[0].id == verified.id
        actor = Actor(id="approver-1", role="approver")
        with pytest.raises(RequestValidationFailed, match="10 characters"):
            decide(db, verified.id, ApprovalDecision.APPROVED, "short", actor)
        approved = decide(
            db,
            verified.id,
            ApprovalDecision.APPROVED,
            "All checks were reviewed.",
            actor,
        )
        assert approved.approver == actor.id
        assert queue(db, limit=10, offset=0).total == 0

        uncertain_schedule = _schedule(
            db,
            inputs=[],
            forecast_meta={},
        )
        forecast = Forecast(
            target="uncertain:target",
            horizon=1,
            points=[
                {
                    "t": datetime.now(UTC).isoformat(),
                    "mean": 10,
                    "lower": 1,
                    "upper": 19,
                }
            ],
            calibration_meta={"target_scale": 10},
            input_versions={},
            high_uncertainty=True,
            version=1,
        )
        db.add(forecast)
        db.flush()
        uncertain_schedule.solver_meta["input_versions"] = [
            {"input_type": "forecast", "input_id": str(forecast.id), "input_version": 1}
        ]
        uncertain_schedule.solver_meta["forecast_meta"] = {"forecast_id": str(forecast.id)}
        uncertain_result = run_checks(db, "schedule", uncertain_schedule.id, "verifier")
        assert uncertain_result.outcome == "uncertain"
        with pytest.raises(ConflictError, match="only when its latest verification is VERIFIED"):
            decide(
                db,
                uncertain_result.id,
                ApprovalDecision.APPROVED,
                "Approve despite uncertainty.",
                actor,
            )
        rejected = decide(
            db,
            uncertain_result.id,
            ApprovalDecision.REJECTED,
            "Needs more evidence before approval.",
            actor,
        )
        assert rejected.decision == "rejected"
        assert get(db, verified.id).id == verified.id
    finally:
        db.close()
        engine.dispose()


def test_audit_query_history_filters_and_small_diff_guard() -> None:
    """Provide stable read-only audit views and reject oversized full-payload snapshots."""
    engine, db = _db()
    try:
        target_id = uuid4()
        now = datetime.now(UTC)
        first = record(db, "schedule", target_id, "created", None, {"version": 1}, "planner")
        first.created_at = now
        second = record(
            db,
            "schedule",
            target_id,
            "verified",
            {"status": "draft"},
            {"status": "verified"},
            "reviewer",
        )
        second.created_at = now + timedelta(seconds=1)
        other = record(db, "record", uuid4(), "created", None, {"version": 1}, "planner")
        db.flush()
        page = query(
            db,
            AuditQuery(entity_type="schedule", entity_id=target_id),
            limit=1,
            offset=0,
        )
        assert page.total == 2
        assert page.items[0].id == second.id
        assert [item.id for item in history(db, "schedule", target_id)] == [first.id, second.id]
        reviewer_entries = query(
            db, AuditQuery(actor="reviewer"), limit=5, offset=0
        ).items
        assert [item.id for item in reviewer_entries] == [second.id]
        assert history(db, "record", other.entity_id) == [other]
        with pytest.raises(ValueError, match="exceeds"):
            record(db, "schedule", target_id, "bad", None, {"payload": "x" * 20_000}, "planner")
        assert not hasattr(AuditEntry, "delete")
    finally:
        db.close()
        engine.dispose()


def test_benchmark_results_filters_nested_metrics_and_ablations() -> None:
    """Read scalar metrics, use experiment rows when MLflow is absent, and compare baseline."""
    engine, db = _db()
    try:
        row = ExperimentRun(
            scenario="heavy_staleness",
            seed=12,
            status="completed",
            config={"severity": 0.5},
            metrics={
                "detection_recall": 0.8,
                "failure_rate": 0.2,
                "baselines": {"no_detection": {"detection_recall": 0.0, "failure_rate": 1.0}},
            },
        )
        incomplete = ExperimentRun(
            scenario="source_conflict",
            seed=1,
            status="running",
            config={},
            metrics={"detection_recall": 0.2},
        )
        db.add_all([row, incomplete])
        db.flush()

        found = results(db, {"scenario": "heavy_staleness", "seed": 12})
        assert len(found) == 1
        assert found[0].id == row.id
        assert found[0].experiment_id == row.id
        assert found[0].metrics == {"detection_recall": 0.8, "failure_rate": 0.2}
        assert results(db, {"scenario": "not-found"}) == []
        comparison = ablations(db)
        assert len(comparison) == 1
        assert comparison[0].name == "heavy_staleness:no_detection"
        assert comparison[0].delta == {"detection_recall": 0.8, "failure_rate": -0.8}
        with pytest.raises(ValueError, match="seed"):
            results(db, {"seed": -1})
    finally:
        db.close()
        engine.dispose()
