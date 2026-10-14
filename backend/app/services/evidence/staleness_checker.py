"""Detect records that exceed configured source freshness thresholds."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.enums import IssueClass, SourceType
from backend.app.db.models.claim import Issue
from backend.app.db.models.record import Record
from backend.app.services.evidence._issue_utils import create_issue_if_missing
from backend.app.services.ingestion.normaliser import to_utc


def is_stale(rec: Record, now: datetime, thresholds: dict[SourceType, int]) -> bool:
    """Determine whether a record is older than its source freshness threshold.

    Args:
        rec: Persisted record to check.
        now: Current aware time.
        thresholds: Maximum age in seconds by source type.

    Returns:
        True if the record age exceeds its configured threshold.
    """
    source_type = SourceType(rec.source_type)
    threshold = thresholds.get(source_type)
    if threshold is None:
        return False
    return (to_utc(now) - to_utc(rec.event_time)).total_seconds() > threshold


def find_stale(db: Session, now: datetime) -> list[Issue]:
    """Find active stale records and persist deduplicated stale issues.

    Args:
        db: Active synchronous database session.
        now: Current aware time used for freshness comparisons.

    Returns:
        Open stale issues corresponding to active stale records.
    """
    settings = get_settings()
    thresholds = {
        source: settings.freshness_thresholds[source.value]
        for source in SourceType
        if source.value in settings.freshness_thresholds
    }
    current = to_utc(now)
    found: list[Issue] = []
    records = db.scalars(select(Record).where(Record.superseded_by.is_(None))).all()
    for record in records:
        if not is_stale(record, current, thresholds):
            continue
        age_seconds = max(0, int((current - to_utc(record.event_time)).total_seconds()))
        found.append(
            create_issue_if_missing(
                db,
                IssueClass.STALE.value,
                [],
                current,
                {
                    "record_id": str(record.id),
                    "entity_id": record.entity_id,
                    "source_type": record.source_type,
                    "age_seconds": age_seconds,
                    "threshold_seconds": thresholds[SourceType(record.source_type)],
                },
            )
        )
    return found
