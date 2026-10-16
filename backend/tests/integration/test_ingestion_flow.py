"""Integration coverage for ingestion replay and invalid-event retention."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.core.enums import SourceType
from backend.app.db.base import Base
from backend.app.db.models import RawEvent, Record
from backend.app.services.ingestion.ingestion_service import ingest_event


def test_replay_thousand_events_creates_no_duplicates_and_retains_invalid_data() -> None:
    """Replay 1,000 synthetic source events without duplicate records."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    event_time = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(engine) as db:
        for index in range(1000):
            ingest_event(
                db,
                SourceType.RESOURCE,
                f"synthetic-{index}",
                event_time,
                {"entity_id": f"resource-{index}", "capacity_mw": float(index)},
            )

        for index in range(1000):
            ingest_event(
                db,
                SourceType.RESOURCE,
                f"synthetic-{index}",
                event_time,
                {"entity_id": f"resource-{index}", "capacity_mw": float(index)},
            )

        invalid = ingest_event(
            db,
            SourceType.RESOURCE,
            "synthetic-invalid",
            event_time,
            {"capacity_mw": "not-a-number"},
        )

        assert len(db.scalars(select(RawEvent)).all()) == 1001
        assert len(db.scalars(select(Record)).all()) == 1001
        assert invalid.flags == ["invalid"]
        assert invalid.normalised_payload["validation_errors"]
    engine.dispose()
