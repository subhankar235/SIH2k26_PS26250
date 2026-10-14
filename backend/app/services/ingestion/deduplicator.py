"""Deterministic exact and ambiguous duplicate classification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

try:
    from enum import StrEnum
except ImportError:  # Python 3.10 compatibility
    from enum import Enum

    class StrEnum(str, Enum):
        """Backport of Python 3.11's StrEnum for older runtimes."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.record import Record
from backend.app.services.ingestion.normaliser import NormalisedRecord, to_utc


class DedupeStatus(StrEnum):
    """Classify how a normalized record relates to persisted records."""

    NEW = "NEW"
    EXACT_DUP = "EXACT_DUP"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class DedupeDecision:
    """Return a deduplication classification and its candidate record, if any."""

    status: DedupeStatus
    record: Record | None = None


def _fingerprint(source_type: str, entity_id: str, payload: dict[str, Any], event_time: Any) -> str:
    """Hash canonical deduplication inputs."""
    canonical = json.dumps(
        {
            "source_type": source_type,
            "entity_id": entity_id,
            "payload": payload,
            "event_time": event_time,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def dedupe_key(rec: NormalisedRecord) -> str:
    """Create a deterministic key for a normalized event.

    Args:
        rec: Normalized record candidate.

    Returns:
        SHA-256 key based on canonical source, identity, content, and event time.
    """
    return _fingerprint(
        rec.source.value,
        rec.entity_id,
        rec.normalised_payload,
        rec.event_time.isoformat(),
    )


def find_duplicate(db: Session, rec: NormalisedRecord) -> Record | None:
    """Find an exact duplicate using the deterministic record key.

    Args:
        db: Active synchronous database session.
        rec: Normalized record candidate.

    Returns:
        The persisted exact duplicate, or None when no exact match exists.
    """
    candidates = db.scalars(
        select(Record).where(
            Record.source_type == rec.source.value,
            Record.entity_id == rec.entity_id,
        )
    )
    target = dedupe_key(rec)
    for candidate in candidates:
        candidate_key = _fingerprint(
            candidate.source_type,
            candidate.entity_id,
            candidate.normalised_payload,
            to_utc(candidate.event_time).isoformat(),
        )
        if candidate_key == target:
            return candidate
    return None


def classify(db: Session, rec: NormalisedRecord) -> DedupeDecision:
    """Classify a record as new, exact, or needing entity matching.

    Args:
        db: Active synchronous database session.
        rec: Normalized record candidate.

    Returns:
        A classification and the relevant candidate record, when available.
    """
    duplicate = find_duplicate(db, rec)
    if duplicate is not None:
        return DedupeDecision(DedupeStatus.EXACT_DUP, duplicate)

    same_entity = db.scalar(
        select(Record)
        .where(
            Record.source_type == rec.source.value,
            Record.entity_id == rec.entity_id,
            Record.superseded_by.is_(None),
        )
        .order_by(Record.version.desc())
        .limit(1)
    )
    if same_entity is not None:
        return DedupeDecision(DedupeStatus.AMBIGUOUS, same_entity)

    payload = rec.normalised_payload
    identity_values = {
        key: str(payload[key]).strip().casefold()
        for key in ("serial_number", "external_id", "name")
        if payload.get(key) not in (None, "")
    }
    if identity_values:
        candidates = db.scalars(
            select(Record).where(
                Record.source_type == rec.source.value,
                Record.superseded_by.is_(None),
            )
        )
        for candidate in candidates:
            if any(
                str(candidate.normalised_payload.get(key, "")).strip().casefold() == value
                for key, value in identity_values.items()
            ):
                return DedupeDecision(DedupeStatus.AMBIGUOUS, candidate)

    return DedupeDecision(DedupeStatus.NEW)
