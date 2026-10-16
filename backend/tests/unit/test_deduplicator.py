"""Tests for exact and ambiguous event deduplication."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core.enums import SourceType
from backend.app.db.base import Base
from backend.app.db.models import Record
from backend.app.services.ingestion.deduplicator import DedupeStatus, classify
from backend.app.services.ingestion.normaliser import NormalisedRecord


def test_deduplicator_returns_new_exact_duplicate_and_ambiguous() -> None:
    """Classify new records, deterministic duplicates, and same-entity changes."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    original = NormalisedRecord(
        source=SourceType.RESOURCE,
        entity_id="resource:r-1",
        normalised_payload={"entity_id": "resource:r-1", "capacity_mw": 4.0},
        event_time=now,
        ingest_time=now,
        extras={},
    )

    with Session(engine) as db:
        assert classify(db, original).status == DedupeStatus.NEW
        persisted = Record(
            entity_id=original.entity_id,
            source_type=SourceType.RESOURCE.value,
            normalised_payload=original.normalised_payload,
            source_id=uuid4(),
            raw_event_id=uuid4(),
            event_time=now,
            ingest_time=now,
        )
        db.add(persisted)
        db.flush()

        assert classify(db, original).status == DedupeStatus.EXACT_DUP
        changed = original.model_copy(
            update={
                "normalised_payload": {"entity_id": original.entity_id, "capacity_mw": 5.0},
                "event_time": now + timedelta(minutes=1),
            }
        )
        decision = classify(db, changed)
        assert decision.status == DedupeStatus.AMBIGUOUS
        assert decision.record is not None and decision.record.id == persisted.id

    engine.dispose()
