"""Trace source origins and version chains for normalized records."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.exceptions import NotFoundError
from backend.app.db.models.record import RawEvent, Record
from backend.app.schemas.evidence import ProvenanceStep
from backend.app.services.ingestion.normaliser import to_utc


def version_chain(db: Session, record_id: UUID) -> list[Record]:
    """Return all persisted versions for the target record's canonical entity.

    Args:
        db: Active synchronous database session.
        record_id: UUID of any version in the chain.

    Returns:
        Records ordered from the earliest to latest version.

    Raises:
        NotFoundError: If the requested record does not exist.
    """
    record = db.get(Record, record_id)
    if record is None:
        raise NotFoundError("Record not found", {"id": str(record_id)})
    return list(
        db.scalars(
            select(Record)
            .where(
                Record.entity_id == record.entity_id,
                Record.source_type == record.source_type,
            )
            .order_by(Record.version, Record.ingest_time, Record.id)
        ).all()
    )


def trace(db: Session, record_id: UUID) -> list[ProvenanceStep]:
    """Trace origin, normalization, and record versions in chronological order.

    Args:
        db: Active synchronous database session.
        record_id: UUID of the target record.

    Returns:
        Provenance timeline from the raw event through persisted versions.

    Raises:
        NotFoundError: If the requested record or its raw event is missing.
    """
    records = version_chain(db, record_id)
    steps: list[ProvenanceStep] = []
    for record in records:
        raw_event = db.get(RawEvent, record.raw_event_id)
        if raw_event is None:
            raise NotFoundError("Raw event not found for record", {"record_id": str(record.id)})
        steps.append(
            ProvenanceStep(
                record_id=record.id,
                action="ingested",
                timestamp=to_utc(raw_event.ingest_time),
                source_id=record.source_id,
                details={"raw_event_id": str(raw_event.id)},
            )
        )
        steps.append(
            ProvenanceStep(
                record_id=record.id,
                action="normalized",
                timestamp=to_utc(record.ingest_time),
                version=record.version,
                source_id=record.source_id,
                details={"event_time": record.event_time.isoformat()},
            )
        )
        if record.superseded_by is not None:
            steps.append(
                ProvenanceStep(
                    record_id=record.id,
                    action="superseded",
                    timestamp=to_utc(record.ingest_time),
                    version=record.version,
                    source_id=record.source_id,
                    details={"superseded_by": str(record.superseded_by)},
                )
            )
    return sorted(steps, key=lambda step: (step.timestamp, step.version or 0, step.action))
