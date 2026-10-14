"""Unit tests for evidence conflict, duplicate, missing, and stale detection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core.enums import IssueClass, SourceType
from backend.app.db.base import Base
from backend.app.db.models import Claim, RawEvent, Record, Source
from backend.app.services.evidence.contradiction_detector import (
    find_conflicts,
    find_duplicates,
    find_missing,
)
from backend.app.services.evidence.staleness_checker import find_stale


def _record_with_claim(
    db: Session,
    source_name: str,
    entity_id: str,
    value: float,
    observed_at: datetime,
) -> tuple[Record, Claim]:
    """Persist a source record and one supporting claim."""
    source = Source(name=source_name, source_type="resource", reliability_prior=0.8)
    db.add(source)
    db.flush()
    raw_event = RawEvent(
        source_id=source.id,
        source_event_id=f"{source_name}-event",
        payload={"entity_id": entity_id, "capacity_mw": value},
        event_time=observed_at,
        ingest_time=observed_at,
    )
    db.add(raw_event)
    db.flush()
    record = Record(
        entity_id=entity_id,
        source_type="resource",
        normalised_payload={"entity_id": entity_id, "capacity_mw": value},
        source_id=source.id,
        raw_event_id=raw_event.id,
        event_time=observed_at,
        ingest_time=observed_at,
    )
    db.add(record)
    db.flush()
    claim = Claim(
        record_id=record.id,
        attribute="capacity_mw",
        value=value,
        source_id=source.id,
        observed_at=observed_at,
    )
    db.add(claim)
    db.flush()
    return record, claim


def test_conflict_and_duplicate_detection_require_multiple_sources() -> None:
    """Identify different simultaneous claims and repeated cross-source values."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as db:
        _, first = _record_with_claim(db, "source-a", "resource:1", 4.0, now)
        _, second = _record_with_claim(db, "source-b", "resource:1", 5.0, now)
        _, third = _record_with_claim(db, "source-c", "resource:1", 4.0, now)

        conflicts = find_conflicts(db, "resource:1", "capacity_mw")
        duplicates = find_duplicates(db)

        assert len(conflicts) == 1
        assert conflicts[0].issue_class == IssueClass.CONFLICT.value
        assert {str(first.id), str(second.id)} <= set(conflicts[0].claim_ids)
        assert len(duplicates) == 1
        assert duplicates[0].issue_class == IssueClass.DUPLICATE.value
        assert str(third.id) in duplicates[0].claim_ids
    engine.dispose()


def test_missing_and_stale_detection_emits_persistent_issues() -> None:
    """Flag absent required fields and stale source records without repeated issues."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as db:
        source = Source(name="source-missing", source_type="resource", reliability_prior=0.8)
        db.add(source)
        db.flush()
        raw_event = RawEvent(
            source_id=source.id,
            source_event_id="missing-event",
            payload={"entity_id": "resource:missing"},
            event_time=now - timedelta(hours=2),
            ingest_time=now - timedelta(hours=2),
        )
        db.add(raw_event)
        db.flush()
        record = Record(
            entity_id="resource:missing",
            source_type="resource",
            normalised_payload={"entity_id": "resource:missing"},
            source_id=source.id,
            raw_event_id=raw_event.id,
            event_time=raw_event.event_time,
            ingest_time=raw_event.ingest_time,
        )
        db.add(record)
        db.flush()

        missing = find_missing(db, {SourceType.RESOURCE: ["capacity_mw"]})
        stale_first = find_stale(db, now)
        stale_second = find_stale(db, now + timedelta(minutes=5))

        assert len(missing) == 1
        assert missing[0].details["missing_fields"] == ["capacity_mw"]
        assert len(stale_first) == len(stale_second) == 1
        assert stale_first[0].id == stale_second[0].id
    engine.dispose()
