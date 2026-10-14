"""Tests for ingestion validation, normalization, matching, and persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.core.enums import SourceType
from backend.app.db.base import Base
from backend.app.db.models import AuditEntry, RawEvent, Record, Source
from backend.app.services.ingestion.deduplicator import DedupeStatus, classify, dedupe_key
from backend.app.services.ingestion.entity_matcher import match
from backend.app.services.ingestion.ingestion_service import ingest_event
from backend.app.services.ingestion.normaliser import NormalisedRecord, normalise, to_utc
from backend.app.services.ingestion.validator import (
    SCHEMAS,
    AvailabilityPayload,
    validate_event,
)


def test_validation_has_a_schema_for_every_source_and_never_raises() -> None:
    """Validate sample payloads and report missing or mistyped fields as errors."""
    assert set(SCHEMAS) == set(SourceType)
    sample_payloads = {
        SourceType.RESOURCE: {"entity_id": "r-1", "capacity_mw": 2.5},
        SourceType.CREW: {"entity_id": "crew-1", "skills": ["repair"]},
        SourceType.AVAILABILITY: {"entity_id": "r-1", "available": True},
        SourceType.WEATHER: {"entity_id": "region-1", "temperature_c": 12.5},
        SourceType.CONSTRAINT: {"entity_id": "grid-1", "constraint_type": "capacity"},
    }

    for source, payload in sample_payloads.items():
        assert validate_event(source, payload).ok
        invalid = validate_event(source, {**payload, "entity_id": 3})
        assert not invalid.ok
        assert invalid.errors
        missing = validate_event(source, {"unrelated": "missing identity"})
        assert not missing.ok
        assert any("entity_id" in error for error in missing.errors)

    missing = validate_event(SourceType.RESOURCE, {"capacity_mw": "not-a-number"})
    assert not missing.ok
    assert any("entity_id" in error for error in missing.errors)


def test_normalization_converts_time_units_ids_and_preserves_unknown_fields() -> None:
    """Canonicalize known fields while retaining unknown source fields as extras."""
    ingest_time = datetime(2026, 1, 2, tzinfo=UTC)
    event_time = datetime(2026, 1, 1, tzinfo=UTC)
    result = validate_event(
        SourceType.RESOURCE,
        {
            "entity_id": "  Unit A  ",
            "event_time": event_time.isoformat(),
            "capacity_kw": 1200,
            "mystery_field": "retained",
        },
    )
    assert result.ok and result.model is not None
    normalized = normalise(
        SourceType.RESOURCE,
        result.model,
        ingest_time,
    )

    assert normalized.entity_id == "resource:unit-a"
    assert normalized.normalised_payload["capacity_mw"] == 1.2
    assert normalized.extras == {"capacity_kw": 1200, "mystery_field": "retained"}
    assert normalized.normalised_payload["extras"] == normalized.extras
    assert normalized.event_time == event_time
    assert normalized.ingest_time == ingest_time
    assert to_utc("2026-01-01T03:00:00+03:00") == event_time


def test_availability_validator_rejects_reversed_window() -> None:
    """Reject invalid temporal windows for availability source payloads."""
    try:
        AvailabilityPayload.model_validate(
            {
                "entity_id": "resource-1",
                "starts_at": "2026-01-02T00:00:00Z",
                "ends_at": "2026-01-01T00:00:00Z",
            }
        )
    except ValueError:
        pass
    else:
        raise AssertionError("reversed availability window was accepted")


def test_deduplication_and_match_thresholds() -> None:
    """Classify a new event and flag uncertain entity matches deterministically."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    candidate = NormalisedRecord(
        source=SourceType.RESOURCE,
        entity_id="resource:one",
        normalised_payload={"entity_id": "resource:one", "name": "Unit One"},
        event_time=now,
        ingest_time=now,
        extras={},
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        assert classify(db, candidate).status == DedupeStatus.NEW
        assert len(dedupe_key(candidate)) == 64
    engine.dispose()

    persisted = Record(
        entity_id="resource:one",
        source_type="resource",
        normalised_payload={"entity_id": "resource:one", "name": "Unit One"},
        source_id=uuid4(),
        raw_event_id=uuid4(),
        event_time=now,
        ingest_time=now,
    )
    same = match(candidate, persisted)
    assert same.is_match and not same.flagged

    different = candidate.model_copy(
        update={"entity_id": "resource:unit-one", "normalised_payload": {"name": "Unit One"}}
    )
    uncertain = match(different, persisted, threshold=0.99, low=0.1)
    assert uncertain.flagged and not uncertain.is_match


def test_ingestion_persists_invalid_events_and_is_idempotent_by_source_event() -> None:
    """Persist and audit good/bad events while replaying a source event only once."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    event_time = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(engine) as db:
        payload = {"entity_id": "resource-1", "capacity_mw": 4.0, "extra": "kept"}
        first = ingest_event(db, SourceType.RESOURCE, "evt-1", event_time, payload)
        repeated = ingest_event(db, SourceType.RESOURCE, "evt-1", event_time, payload)
        exact_duplicate = ingest_event(db, SourceType.RESOURCE, "evt-2", event_time, payload)
        invalid = ingest_event(
            db,
            SourceType.RESOURCE,
            "evt-invalid",
            event_time,
            {"capacity_mw": "bad"},
        )

        assert first.id == repeated.id == exact_duplicate.id
        assert invalid.flags == ["invalid"]
        assert "validation_errors" in invalid.normalised_payload
        assert invalid.normalised_payload["validation_errors"]
        assert first.normalised_payload["extras"]["extra"] == "kept"
        assert len(db.scalars(select(RawEvent)).all()) == 3
        assert len(db.scalars(select(Record)).all()) == 2
        assert len(db.scalars(select(AuditEntry)).all()) >= 6
        assert db.scalar(select(Source).where(Source.source_type == "resource")) is not None
    engine.dispose()
