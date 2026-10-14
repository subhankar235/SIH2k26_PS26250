"""Tests for A5.3 validity and A5.4 forecasting service behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.core.enums import ValidityStatus
from backend.app.core.exceptions import ConflictError, RequestValidationFailed
from backend.app.db.base import Base
from backend.app.db.models import (
    AuditEntry,
    Decision,
    Forecast,
    RawEvent,
    Record,
    Schedule,
    Source,
    VerificationResult,
)
from backend.app.schemas.forecast import ForecastOut
from backend.app.schemas.validity import AssumptionIn, ChangeEvent, CheckResult, InputRef
from backend.app.services.forecasting.calibration import (
    coverage,
    ece,
    flag_high_uncertainty,
    nll,
)
from backend.app.services.forecasting.features import build_features
from backend.app.services.forecasting.predictor import create_forecast, get
from backend.app.services.validity import status as validity_status
from backend.app.services.validity.assumption_tracker import envelope, register_decision
from backend.app.services.validity.change_detector import changed_inputs_since, detect_changes
from backend.app.services.validity.dependency_graph import (
    affected_decisions,
    build,
    descendants_only,
)
from backend.app.services.validity.reverifier import reverify, reverify_full
from backend.app.services.validity.status import evaluate, transition


def _engine_and_record() -> tuple[object, UUID, UUID]:
    """Create an in-memory schema and a version-one synthetic input record."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(engine) as db:
        source = Source(name="validity-source", source_type="resource", reliability_prior=0.8)
        db.add(source)
        db.flush()
        raw = RawEvent(
            source_id=source.id,
            source_event_id="validity-event",
            payload={"entity_id": "resource:validity", "value": 1},
            event_time=timestamp,
            ingest_time=timestamp,
        )
        db.add(raw)
        db.flush()
        record = Record(
            entity_id="resource:validity",
            source_type="resource",
            normalised_payload={"entity_id": "resource:validity", "value": 1},
            source_id=source.id,
            raw_event_id=raw.id,
            event_time=timestamp,
            ingest_time=timestamp,
        )
        db.add(record)
        db.commit()
        result = (engine, record.id, source.id)
    return result


def _decision_for_record(db: Session, record_id: UUID):
    """Register one decision with an assumption and a record dependency."""
    return register_decision(
        db,
        decision_type="schedule",
        ref_id=UUID(int=50),
        inputs=[InputRef(input_type="record", input_id=record_id, input_version=1)],
        assumptions=[
            AssumptionIn(description="resource remains available", parameters={"reserve": 1})
        ],
    )


def _branching_reverify_state() -> tuple[object, list[UUID], dict[str, UUID]]:
    """Build branched dependencies, one unrelated decision, and one terminal decision."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(engine) as db:
        source = Source(name="branch-source", source_type="resource", reliability_prior=0.8)
        db.add(source)
        db.flush()
        record_ids: list[UUID] = []
        for suffix in "abcd":
            raw = RawEvent(
                source_id=source.id,
                source_event_id=f"branch-{suffix}",
                payload={"entity_id": f"resource:{suffix}", "value": 1},
                event_time=timestamp,
                ingest_time=timestamp,
            )
            db.add(raw)
            db.flush()
            record = Record(
                entity_id=f"resource:{suffix}",
                source_type="resource",
                normalised_payload={"entity_id": f"resource:{suffix}", "value": 1},
                source_id=source.id,
                raw_event_id=raw.id,
                event_time=timestamp,
                ingest_time=timestamp,
            )
            db.add(record)
            db.flush()
            record_ids.append(record.id)

        refs = {
            "branch": UUID(int=101),
            "left": UUID(int=102),
            "terminal": UUID(int=103),
            "unrelated": UUID(int=104),
        }
        decisions = {
            "branch": register_decision(
                db,
                "schedule",
                refs["branch"],
                [
                    InputRef(input_type="record", input_id=record_ids[0], input_version=1),
                    InputRef(input_type="record", input_id=record_ids[1], input_version=1),
                ],
                [AssumptionIn(description="two inputs support this decision")],
            ),
            "left": register_decision(
                db,
                "forecast",
                refs["left"],
                [InputRef(input_type="record", input_id=record_ids[0], input_version=1)],
                [AssumptionIn(description="left input remains current")],
            ),
            "terminal": register_decision(
                db,
                "approval",
                refs["terminal"],
                [InputRef(input_type="record", input_id=record_ids[2], input_version=1)],
                [AssumptionIn(description="terminal decision input")],
            ),
            "unrelated": register_decision(
                db,
                "audit",
                refs["unrelated"],
                [InputRef(input_type="record", input_id=record_ids[3], input_version=1)],
                [AssumptionIn(description="unrelated input remains current")],
            ),
        }
        terminal = decisions["terminal"]
        transition(db, terminal, ValidityStatus.STALE, "prepared for invalidation", "test")
        transition(db, terminal, ValidityStatus.INVALIDATED, "test invalidation", "test")
        for record_id in record_ids[:3]:
            record = db.get(Record, record_id)
            assert record is not None
            record.version = 2
            record.ingest_time = timestamp + timedelta(days=1)
        db.commit()
    return engine, record_ids, refs


def test_dependency_graph_and_envelope_cover_input_assumption_decision() -> None:
    """Build the directed dependency chain and return its complete envelope."""
    engine, record_id, _ = _engine_and_record()
    with Session(engine) as db:
        decision = _decision_for_record(db, record_id)
        graph = build(db)
        input_node = f"input:record:{record_id}:v1"
        descendants = descendants_only(graph, input_node)
        affected = affected_decisions(
            graph,
            [InputRef(input_type="record", input_id=record_id, input_version=2)],
        )
        item = envelope(db, decision.id)

        assert len(descendants) == 2
        assert affected == {decision.id}
        assert item.version == 1
        assert item.status == ValidityStatus.UNCERTAIN
        assert len(item.assumptions) == len(item.dependencies) == 1
        assert item.verification is None

        db.add(
            VerificationResult(
                target_type="schedule",
                target_id=decision.ref_id,
                outcome="verified",
                violations=[],
                uncertainty_flags=[],
                checked_at=datetime(2026, 1, 2, tzinfo=UTC),
            )
        )
        db.flush()
        item = envelope(db, decision.id)
        assert item.verification is not None
        assert item.verification.outcome.value == "verified"
        assert descendants_only(graph, "not-present") == set()
        assert not affected_decisions(
            graph,
            [InputRef(input_type="record", input_id=record_id, input_version=1)],
        )
    engine.dispose()


def test_incremental_reverify_matches_full_recompute_and_audits_transitions() -> None:
    """Use separate equivalent databases to compare incremental and full outcomes."""
    outcomes: list[tuple[str, list[tuple[str, str]], int]] = []
    for full in (False, True):
        engine, record_id, _ = _engine_and_record()
        with Session(engine) as db:
            decision = _decision_for_record(db, record_id)
            record = db.get(Record, record_id)
            assert record is not None
            record.version = 2
            record.ingest_time = datetime(2026, 1, 2, tzinfo=UTC)
            db.flush()
            if full:
                result = reverify_full(db)
            else:
                result = reverify(
                    db,
                    [
                        ChangeEvent(
                            input_type="record",
                            input_id=record_id,
                            old_version=1,
                            new_version=2,
                            changed_at=datetime(2026, 1, 2, tzinfo=UTC),
                        )
                    ],
                )
            current = db.get(type(decision), decision.id)
            assert current is not None
            audit_count = len(db.scalars(select(AuditEntry)).all())
            audit = db.scalar(
                select(AuditEntry).where(
                    AuditEntry.entity_type == "decision",
                    AuditEntry.entity_id == decision.id,
                    AuditEntry.action == "validity_transition",
                )
            )
            assert audit is not None
            assert audit.actor == "reverification"
            assert audit.before_ref == {"status": "uncertain", "version": 1}
            assert audit.after_ref["reason"] == "A dependent input version changed"
            assert audit.created_at.tzinfo is not None
            outcomes.append(
                (
                    current.status,
                    [
                        (item.old_status.value, item.new_status.value)
                        for item in result.status_changes
                    ],
                    result.nodes_touched,
                )
            )
            assert audit_count >= 2
        engine.dispose()

    assert outcomes[0] == outcomes[1]
    assert outcomes[0][0] == ValidityStatus.STALE.value


def test_incremental_matches_full_for_branches_duplicates_and_invalidated_decisions() -> None:
    """Handle branching changes, duplicate events, unrelated, and terminal decisions."""
    results: list[tuple[dict[UUID, str], set[UUID], int, list[UUID]]] = []
    for full in (False, True):
        engine, record_ids, decision_refs = _branching_reverify_state()
        with Session(engine) as db:
            if full:
                result = reverify_full(db)
            else:
                result = reverify(
                    db,
                    [
                        ChangeEvent(
                            input_type="record",
                            input_id=record_ids[0],
                            old_version=1,
                            new_version=2,
                        ),
                        ChangeEvent(
                            input_type="record",
                            input_id=record_ids[0],
                            old_version=1,
                            new_version=2,
                        ),
                        ChangeEvent(
                            input_type="record",
                            input_id=record_ids[1],
                            old_version=1,
                            new_version=2,
                        ),
                        ChangeEvent(
                            input_type="record",
                            input_id=record_ids[2],
                            old_version=1,
                            new_version=2,
                        ),
                    ],
                )
            decisions = list(db.scalars(select(Decision)))
            status_by_ref = {decision.ref_id: decision.status for decision in decisions}
            ref_by_id = {decision.id: decision.ref_id for decision in decisions}
            results.append(
                (
                    status_by_ref,
                    {ref_by_id[item] for item in result.affected},
                    result.nodes_touched,
                    {ref_by_id[item] for item in result.skipped_invalidated},
                )
            )
        engine.dispose()

    assert results[0][0] == results[1][0]
    assert results[0][2] < results[1][2]
    assert results[0][1] == {
        decision_refs["branch"],
        decision_refs["left"],
        decision_refs["terminal"],
    }
    assert results[0][3] == {decision_refs["terminal"]}
    assert results[0][0][decision_refs["branch"]] == ValidityStatus.STALE.value
    assert results[0][0][decision_refs["left"]] == ValidityStatus.STALE.value
    assert results[0][0][decision_refs["terminal"]] == ValidityStatus.INVALIDATED.value
    assert results[0][0][decision_refs["unrelated"]] == ValidityStatus.UNCERTAIN.value


def test_validity_state_machine_and_check_evaluation() -> None:
    """Enforce legal transitions and classify failed or uncertain checks."""
    engine, record_id, _ = _engine_and_record()
    with Session(engine) as db:
        decision = _decision_for_record(db, record_id)
        assert evaluate(decision, []) == ValidityStatus.UNCERTAIN
        assert evaluate(decision, [CheckResult(valid=False)]) == ValidityStatus.INVALIDATED
        assert evaluate(decision, [CheckResult(valid=True)]) == ValidityStatus.VERIFIED
        assert (
            evaluate(
                decision,
                [
                    CheckResult(name="capacity", valid=True),
                    CheckResult(name="capacity", valid=False),
                ],
            )
            == ValidityStatus.INVALIDATED
        )
        assert (
            evaluate(
                decision,
                [CheckResult(name="conflicting-evidence", valid=True, contradictory=True)],
            )
            == ValidityStatus.INVALIDATED
        )
        assert (
            evaluate(decision, [CheckResult(name="missing", complete=False)])
            == ValidityStatus.UNCERTAIN
        )
        assert (
            evaluate(
                decision,
                [CheckResult(name="optional", valid=False, required=False)],
            )
            == ValidityStatus.UNCERTAIN
        )
        with pytest.raises(RequestValidationFailed):
            transition(db, decision, ValidityStatus.STALE, " ", "tester")
        with pytest.raises(RequestValidationFailed):
            transition(db, decision, ValidityStatus.STALE, "input changed", " ")

        decision = transition(db, decision, ValidityStatus.STALE, "input changed", "tester")
        decision = transition(db, decision, ValidityStatus.VERIFIED, "checks passed", "tester")
        assert decision.status == ValidityStatus.VERIFIED.value
        with pytest.raises(ConflictError):
            transition(db, decision, ValidityStatus.INVALIDATED, "failed", "tester")

        decision = transition(db, decision, ValidityStatus.STALE, "new input changed", "tester")
        decision = transition(db, decision, ValidityStatus.INVALIDATED, "check failed", "tester")
        with pytest.raises(ConflictError):
            transition(db, decision, ValidityStatus.STALE, "retry", "tester")
    engine.dispose()


def test_change_detection_is_reproducible_and_since_returns_current_versions() -> None:
    """Call BOCPD reproducibly and identify newly ingested input versions."""
    series = {"load": np.concatenate((np.zeros(20), np.full(20, 10.0)))}
    first = detect_changes(series, hazard=0.1, seed=9)
    second = detect_changes(series, hazard=0.1, seed=9)
    assert first == second
    assert all(point.series == "load" and 0 <= point.index < 40 for point in first)
    assert any(18 <= point.index <= 22 for point in first)
    with pytest.raises(ValueError, match="at least one"):
        detect_changes({})
    with pytest.raises(ValueError, match="three observations"):
        detect_changes({"too_short": np.array([1.0, 2.0])})
    with pytest.raises(ValueError, match="finite"):
        detect_changes({"non_finite": np.array([1.0, np.nan, 3.0])})
    with pytest.raises(ValueError, match="lam"):
        detect_changes(series, hazard=0.0)

    engine, record_id, _ = _engine_and_record()
    with Session(engine) as db:
        record = db.get(Record, record_id)
        assert record is not None
        record.version = 2
        record.ingest_time = datetime(2026, 1, 2, tzinfo=UTC)
        db.flush()
        changed = changed_inputs_since(db, datetime(2026, 1, 1, tzinfo=UTC))
        assert changed == [InputRef(input_type="record", input_id=record_id, input_version=2)]
    engine.dispose()


def test_superseded_record_events_map_back_to_registered_input_ids() -> None:
    """Map a new record id to the old dependency id across a version lineage."""
    engine, record_id, source_id = _engine_and_record()
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(engine) as db:
        decision = _decision_for_record(db, record_id)
        old = db.get(Record, record_id)
        assert old is not None
        new_raw = RawEvent(
            source_id=source_id,
            source_event_id="validity-event-v2",
            payload={"entity_id": "resource:validity", "value": 2},
            event_time=timestamp + timedelta(days=1),
            ingest_time=timestamp + timedelta(days=1),
        )
        db.add(new_raw)
        db.flush()
        new_record = Record(
            entity_id=old.entity_id,
            source_type=old.source_type,
            normalised_payload={"entity_id": old.entity_id, "value": 2},
            version=2,
            source_id=source_id,
            raw_event_id=new_raw.id,
            event_time=new_raw.event_time,
            ingest_time=new_raw.ingest_time,
        )
        db.add(new_record)
        db.flush()
        old.superseded_by = new_record.id
        db.commit()

        refs = changed_inputs_since(db, timestamp)
        assert InputRef(input_type="record", input_id=record_id, input_version=2) in refs
        result = reverify(
            db,
            [
                ChangeEvent(
                    input_type="record",
                    input_id=new_record.id,
                    old_version=1,
                    new_version=2,
                    changed_at=timestamp + timedelta(days=1),
                )
            ],
        )
        db.refresh(decision)
        assert decision.status == ValidityStatus.STALE.value
        assert decision.id in result.affected
    engine.dispose()


def test_historical_input_registration_starts_stale() -> None:
    """Keep an explicit historical input version and mark its decision stale."""
    engine, record_id, source_id = _engine_and_record()
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(engine) as db:
        old = db.get(Record, record_id)
        assert old is not None
        new_raw = RawEvent(
            source_id=source_id,
            source_event_id="historical-v2",
            payload={"entity_id": old.entity_id, "value": 2},
            event_time=timestamp + timedelta(days=1),
            ingest_time=timestamp + timedelta(days=1),
        )
        db.add(new_raw)
        db.flush()
        current = Record(
            entity_id=old.entity_id,
            source_type=old.source_type,
            normalised_payload={"entity_id": old.entity_id, "value": 2},
            version=2,
            source_id=source_id,
            raw_event_id=new_raw.id,
            event_time=new_raw.event_time,
            ingest_time=new_raw.ingest_time,
        )
        db.add(current)
        db.flush()
        old.superseded_by = current.id
        db.flush()
        decision = register_decision(
            db,
            "historical-schedule",
            UUID(int=900),
            [InputRef(input_type="record", input_id=old.id, input_version=1)],
            [AssumptionIn(description="historical input captured")],
        )
        assert decision.status == ValidityStatus.STALE.value
    engine.dispose()


def test_decision_registration_deduplicates_aliases_and_rejects_conflicting_versions() -> None:
    """Store one logical dependency and reject ambiguous versions for the same UUID."""
    engine, record_id, _ = _engine_and_record()
    with Session(engine) as db:
        decision = register_decision(
            db,
            "schedule",
            UUID(int=901),
            [
                InputRef(input_type="record", input_id=record_id, input_version=1),
                InputRef(input_type="resource", input_id=record_id, input_version=1),
            ],
            [AssumptionIn(description="shared logical input")],
        )
        assert len(envelope(db, decision.id).dependencies) == 1

        with pytest.raises(ConflictError):
            register_decision(
                db,
                "schedule",
                UUID(int=902),
                [
                    InputRef(input_type="record", input_id=record_id, input_version=1),
                    InputRef(input_type="resource", input_id=record_id, input_version=2),
                ],
                [AssumptionIn(description="conflicting input versions")],
            )
    engine.dispose()


def test_transition_rolls_back_state_when_audit_write_fails(monkeypatch) -> None:
    """Keep status and audit atomic if audit persistence fails."""
    engine, record_id, _ = _engine_and_record()
    with Session(engine) as db:
        decision = _decision_for_record(db, record_id)

        def fail_audit(*args: object, **kwargs: object) -> None:
            raise RuntimeError("audit storage unavailable")

        monkeypatch.setattr(validity_status, "audit_record", fail_audit)
        with pytest.raises(RuntimeError, match="audit storage"):
            transition(db, decision, ValidityStatus.STALE, "input changed", "tester")
        db.expire_all()
        persisted = db.get(Decision, decision.id)
        assert persisted is not None
        assert persisted.status == ValidityStatus.UNCERTAIN.value
        assert persisted.version == 1
        transition_audits = db.scalars(
            select(AuditEntry).where(
                AuditEntry.entity_id == persisted.id,
                AuditEntry.action == "validity_transition",
            )
        ).all()
        assert transition_audits == []
    engine.dispose()


def test_forecast_features_are_past_only_and_end_to_end_fallback_persists_versions() -> None:
    """Forecast synthetic history recursively through the ARIMA fallback."""
    index = pd.date_range("2026-01-01", periods=4, freq="h", tz="UTC")
    frame = pd.DataFrame(
        {
            "load": [1.0, 2.0, 3.0, 1000.0],
            "temperature_c": [10.0, 20.0, 30.0, 999.0],
        },
        index=index,
    )
    features = build_features(frame, "load", lags=[1, 2], windows=[3])
    assert "load" not in features
    assert features.iloc[2]["load_lag_1"] == 2.0
    assert features.iloc[2]["load_rolling_mean_3"] == 1.5
    assert features.iloc[3]["temperature_c_lag_1"] == 30.0
    with pytest.raises(ValueError, match="chronological"):
        build_features(frame.iloc[::-1], "load", lags=[1], windows=[1])
    with pytest.raises(ValueError, match="duplicate columns"):
        build_features(
            pd.DataFrame([[1.0, 2.0]], columns=["load", "load"]),
            "load",
            lags=[1],
            windows=[1],
        )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source = Source(name="forecast-source", source_type="resource", reliability_prior=0.8)
        db.add(source)
        db.flush()
        for index_value, (timestamp, value) in enumerate(
            zip(index, [1.0, 2.0, 3.0, 4.0], strict=True)
        ):
            raw_event = RawEvent(
                source_id=source.id,
                source_event_id=f"forecast-event-{index_value}",
                payload={"entity_id": "resource:forecast", "load_mw": value},
                event_time=timestamp.to_pydatetime(),
                ingest_time=timestamp.to_pydatetime(),
            )
            db.add(raw_event)
            db.flush()
            db.add(
                Record(
                    entity_id="resource:forecast",
                    source_type="resource",
                    normalised_payload={"entity_id": "resource:forecast", "load_mw": value},
                    source_id=source.id,
                    raw_event_id=raw_event.id,
                    event_time=timestamp.to_pydatetime(),
                    ingest_time=timestamp.to_pydatetime(),
                    version=index_value + 1,
                )
            )
        db.flush()

        first = create_forecast(db, "resource:forecast.load_mw", 3, seed=42)
        second = create_forecast(db, "resource:forecast.load_mw", 3, seed=42)

        assert first.version == 1 and second.version == 2
        assert len(first.points) == 3
        assert first.points == second.points
        assert first.calibration_meta["selected_model"] == "arima"
        assert len(first.calibration_meta["fallback_reasons"]) == 2
        assert first.calibration_meta["calibration_method"] == "rolling_origin_conformal_90"
        assert len(first.input_versions) == 4
        assert len(ForecastOut.model_validate(first).points) == 3
        assert get(db, first.id).id == first.id
        changed_inputs = changed_inputs_since(db, datetime(2026, 1, 1, tzinfo=UTC))
        assert any(
            item.input_type == "forecast" and item.input_id == first.id for item in changed_inputs
        )
        assert first.created_at.tzinfo is not None
        uncertainty_probe = Forecast(
            target="probe",
            horizon=1,
            points=[{"t": "2026-01-01T00:00:00Z", "mean": 0, "lower": -1, "upper": 1}],
            calibration_meta={},
            input_versions={},
            high_uncertainty=True,
        )
        assert flag_high_uncertainty(uncertainty_probe, threshold=0.5)
        schedule = Schedule(
            assignments=[],
            objectives={},
            solver_meta={},
            status="draft",
            problem_hash="synthetic-problem",
        )
        db.add(schedule)
        db.flush()
        recent = changed_inputs_since(db, datetime.now(UTC) - timedelta(minutes=1))
        assert any(item.input_type == "forecast" and item.input_id == first.id for item in recent)
        assert any(
            item.input_type == "schedule" and item.input_id == schedule.id for item in recent
        )
    engine.dispose()


def test_forecast_calibration_metrics() -> None:
    """Compute coverage, ECE, and Gaussian NLL on aligned forecast data."""
    observed = np.array([1.0, 2.0, 3.0])
    means = np.array([1.0, 2.0, 2.0])
    std = np.array([0.5, 0.5, 1.0])
    assert coverage(observed, means - 1.0, means + 1.0) == 1.0
    assert ece(observed, means, std, bins=2) >= 0.0
    assert np.isfinite(nll(observed, means, std))
    with pytest.raises(ValueError):
        coverage(observed, means + 1, means)
    with pytest.raises(ValueError, match="finite"):
        coverage(np.array([np.nan]), np.array([0.0]), np.array([1.0]))
    with pytest.raises(ValueError, match="same non-zero shape"):
        coverage(np.array([[1.0]]), np.array([0.0]), np.array([1.0]))
