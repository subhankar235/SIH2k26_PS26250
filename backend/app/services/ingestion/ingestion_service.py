"""Transactional ingestion orchestration."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.enums import SourceType
from backend.app.core.exceptions import ConflictError
from backend.app.db.models.record import RawEvent, Record
from backend.app.db.models.source import Source
from backend.app.schemas.common import Page
from backend.app.schemas.ingestion import (
    FlaggedRecordOut,
    IngestStatusOut,
    RecordOut,
    TopicStatus,
)
from backend.app.services.audit.audit_service import record as audit_record
from backend.app.services.ingestion.deduplicator import DedupeStatus, classify
from backend.app.services.ingestion.entity_matcher import match
from backend.app.services.ingestion.normaliser import (
    NormalisedRecord,
    canonical_entity_id,
    normalise,
    to_utc,
)
from backend.app.services.ingestion.validator import validate_event


def _source_for(db: Session, source_type: SourceType) -> Source:
    """Find or create the configured source used for an enum source type."""
    source = db.scalar(
        select(Source)
        .where(Source.source_type == source_type.value)
        .order_by(Source.name, Source.id)
        .limit(1)
    )
    if source is not None:
        return source

    source = Source(name=source_type.value, source_type=source_type.value, reliability_prior=0.5)
    db.add(source)
    db.flush()
    audit_record(
        db,
        "source",
        source.id,
        "created",
        None,
        {"name": source.name, "source_type": source.source_type},
        "ingestion",
    )
    return source


def _record_for_raw_event(db: Session, raw_event_id: uuid.UUID) -> Record | None:
    """Return the record already produced from a raw event."""
    return db.scalar(select(Record).where(Record.raw_event_id == raw_event_id))


def _invalid_record(
    source: SourceType,
    source_event_id: str,
    event_time: datetime,
    ingest_time: datetime,
    payload: dict[str, Any],
    errors: list[str],
) -> NormalisedRecord:
    """Preserve an invalid payload in a canonical record envelope."""
    raw_id = str(
        payload.get("entity_id")
        or payload.get("asset_id")
        or payload.get("crew_id")
        or source_event_id
    )
    entity_id = canonical_entity_id(source, raw_id)
    normalized_payload = jsonable_encoder(payload)
    normalized_payload["entity_id"] = entity_id
    normalized_payload["validation_errors"] = errors
    return NormalisedRecord(
        source=source,
        entity_id=entity_id,
        normalised_payload=normalized_payload,
        event_time=event_time,
        ingest_time=ingest_time,
        extras={},
    )


def _persist_record(
    db: Session,
    source_row: Source,
    raw_event: RawEvent,
    candidate: NormalisedRecord,
    flags: list[str],
    version: int = 1,
) -> Record:
    """Persist a normalized record and its audit reference."""
    record = Record(
        entity_id=candidate.entity_id,
        source_type=candidate.source.value,
        normalised_payload=candidate.normalised_payload,
        version=version,
        source_id=source_row.id,
        raw_event_id=raw_event.id,
        event_time=candidate.event_time,
        ingest_time=candidate.ingest_time,
        flags=flags,
    )
    db.add(record)
    db.flush()
    audit_record(
        db,
        "record",
        record.id,
        "created",
        None,
        {
            "entity_id": record.entity_id,
            "source_type": record.source_type,
            "version": record.version,
            "flags": record.flags,
        },
        "ingestion",
    )
    return record


def ingest_event(
    db: Session,
    source: SourceType,
    source_event_id: str,
    event_time: datetime,
    payload: dict[str, Any],
) -> Record:
    """Store, validate, normalize, deduplicate, and audit a source event.

    Args:
        db: Active synchronous database session.
        source: Source category for the event.
        source_event_id: Source-unique event identifier.
        event_time: Aware event timestamp.
        payload: Original source payload; invalid payloads are retained and flagged.

    Returns:
        The normalized persisted record, or the existing record for an exact duplicate.

    Raises:
        ConflictError: If an idempotent raw event exists without its completed record.
        ValueError: If timestamps or identifiers cannot be normalized.
    """
    normalized_event_time = to_utc(event_time)
    ingest_time = datetime.now(UTC)
    source_row = _source_for(db, source)
    existing_raw = db.scalar(
        select(RawEvent).where(
            RawEvent.source_id == source_row.id,
            RawEvent.source_event_id == source_event_id,
        )
    )
    if existing_raw is not None:
        existing_record = _record_for_raw_event(db, existing_raw.id)
        if existing_record is None:
            raise ConflictError(
                "Raw event already exists but its record was not completed",
                {"raw_event_id": str(existing_raw.id)},
            )
        return existing_record

    raw_event = RawEvent(
        source_id=source_row.id,
        source_event_id=source_event_id,
        payload=jsonable_encoder(payload),
        event_time=normalized_event_time,
        ingest_time=ingest_time,
    )
    try:
        with db.begin_nested():
            db.add(raw_event)
            db.flush()
    except IntegrityError:
        # The unique source/event constraint handles concurrent replays.
        existing_raw = db.scalar(
            select(RawEvent).where(
                RawEvent.source_id == source_row.id,
                RawEvent.source_event_id == source_event_id,
            )
        )
        if existing_raw is None:
            raise
        existing_record = _record_for_raw_event(db, existing_raw.id)
        if existing_record is None:
            raise ConflictError("Concurrent raw event has not produced a record") from None
        return existing_record

    audit_record(
        db,
        "raw_event",
        raw_event.id,
        "stored",
        None,
        {"source_id": str(source_row.id), "source_event_id": source_event_id},
        "ingestion",
    )

    result = validate_event(source, payload)
    if result.ok and result.model is not None:
        model = result.model.model_copy(update={"event_time": normalized_event_time})
        normalized = normalise(source, model, ingest_time)
        flags: list[str] = []
    else:
        normalized = _invalid_record(
            source,
            source_event_id,
            normalized_event_time,
            ingest_time,
            payload,
            result.errors,
        )
        flags = ["invalid"]

    dedupe = classify(db, normalized)
    if dedupe.status == DedupeStatus.EXACT_DUP and dedupe.record is not None:
        return dedupe.record

    version = 1
    previous = None
    if dedupe.status == DedupeStatus.AMBIGUOUS and dedupe.record is not None and not flags:
        matched = match(normalized, dedupe.record)
        if matched.is_match:
            previous = dedupe.record
            normalized = normalized.model_copy(
                update={
                    "entity_id": previous.entity_id,
                    "normalised_payload": {
                        **normalized.normalised_payload,
                        "entity_id": previous.entity_id,
                    },
                }
            )
            version = previous.version + 1
        elif matched.flagged:
            flags.append("ambiguous_match")
            normalized.normalised_payload["match_review"] = {
                "candidate_record_id": str(dedupe.record.id),
                "probability": matched.probability,
            }

    record = _persist_record(db, source_row, raw_event, normalized, flags, version)
    if previous is not None:
        previous.superseded_by = record.id
        db.flush()
        audit_record(
            db,
            "record",
            previous.id,
            "superseded",
            {"superseded_by": None, "version": previous.version},
            {"superseded_by": str(record.id), "version": previous.version},
            "ingestion",
        )
    return record


def get_status(db: Session) -> IngestStatusOut:
    """Return configured ingestion topic health.

    Args:
        db: Active synchronous database session.

    Returns:
        A status entry for every source type.

    Raises:
        SQLAlchemyError: If the source lookup fails.
    """
    configured = set(db.scalars(select(Source.source_type)).all())
    return IngestStatusOut(
        topics=[
            TopicStatus(
                topic=source.value,
                status="configured" if source.value in configured else "unconfigured",
                lag=0,
            )
            for source in SourceType
        ]
    )


def list_flagged(db: Session, limit: int, offset: int) -> Page[FlaggedRecordOut]:
    """List active records carrying validation or ambiguous-match flags.

    Args:
        db: Active synchronous database session.
        limit: Maximum number of results to return.
        offset: Number of matching results to skip.

    Returns:
        A page of flagged records with human-readable review reasons.

    Raises:
        ValueError: If limit or offset is invalid.
        SQLAlchemyError: If the record query fails.
    """
    if limit < 1 or offset < 0:
        raise ValueError("limit must be positive and offset must not be negative")
    records = db.scalars(
        select(Record)
        .where(Record.superseded_by.is_(None))
        .order_by(Record.ingest_time.desc(), Record.id)
    ).all()
    flagged = [record for record in records if record.flags]
    page_items = [
        FlaggedRecordOut(
            record=RecordOut(
                id=record.id,
                entity_id=record.entity_id,
                source_type=SourceType(record.source_type),
                normalised_payload=record.normalised_payload,
                version=record.version,
                source_id=record.source_id,
                raw_event_id=record.raw_event_id,
                event_time=to_utc(record.event_time),
                ingest_time=to_utc(record.ingest_time),
                flags=record.flags,
                superseded_by=record.superseded_by,
            ),
            reasons=(
                record.normalised_payload.get("validation_errors", [])
                if "invalid" in record.flags
                else ["Potentially ambiguous entity match"]
            ),
        )
        for record in flagged[offset : offset + limit]
    ]
    return Page[FlaggedRecordOut](
        items=page_items,
        total=len(flagged),
        limit=limit,
        offset=offset,
    )
