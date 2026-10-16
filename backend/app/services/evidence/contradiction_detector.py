"""Detect conflicts, duplicate claims, missing fields, and staleness."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.enums import IssueClass, SourceType
from backend.app.db.models.claim import Claim, Issue
from backend.app.db.models.record import Record
from backend.app.services.evidence._issue_utils import create_issue_if_missing
from backend.app.services.evidence.staleness_checker import find_stale
from backend.app.services.ingestion.normaliser import to_utc

DEFAULT_REQUIRED_FIELDS: dict[SourceType, list[str]] = {
    SourceType.RESOURCE: ["entity_id"],
    SourceType.CREW: ["entity_id"],
    SourceType.AVAILABILITY: ["entity_id"],
    SourceType.WEATHER: ["entity_id"],
    SourceType.CONSTRAINT: ["entity_id"],
}


def _json_key(value: Any) -> str:
    """Serialize a claim value for stable equality checks."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def find_conflicts(
    db: Session,
    entity_id: str,
    attribute: str | None = None,
) -> list[Issue]:
    """Find simultaneously active, cross-source claims with different values.

    Args:
        db: Active synchronous database session.
        entity_id: Canonical entity id to inspect.
        attribute: Optional attribute filter.

    Returns:
        Open conflict issues for matching entity attributes.

    Raises:
        SQLAlchemyError: If claims or issues cannot be queried or persisted.
    """
    statement = (
        select(Claim, Record)
        .join(Record, Claim.record_id == Record.id)
        .where(
            Record.entity_id == entity_id,
            Record.superseded_by.is_(None),
            Claim.superseded_by.is_(None),
        )
    )
    if attribute is not None:
        statement = statement.where(Claim.attribute == attribute)

    groups: dict[str, list[tuple[Claim, Record]]] = defaultdict(list)
    for claim, record in db.execute(statement):
        groups[claim.attribute].append((claim, record))

    now = datetime.now(UTC)
    issues: list[Issue] = []
    for field, claims in groups.items():
        values = {_json_key(claim.value) for claim, _ in claims}
        sources = {claim.source_id for claim, _ in claims}
        if len(values) < 2 or len(sources) < 2:
            continue
        claim_ids = [claim.id for claim, _ in claims]
        claim_details = [
            {
                "claim_id": str(claim.id),
                "record_id": str(claim.record_id),
                "attribute": claim.attribute,
                "value": claim.value,
                "source_id": str(claim.source_id),
                "observed_at": to_utc(claim.observed_at).isoformat(),
            }
            for claim, _ in claims
        ]
        issues.append(
            create_issue_if_missing(
                db,
                IssueClass.CONFLICT.value,
                claim_ids,
                now,
                {
                    "entity_id": entity_id,
                    "attribute": field,
                    "claim_ids": [str(claim_id) for claim_id in claim_ids],
                    "claims": claim_details,
                    "overlapping_validity": True,
                },
            )
        )
    return issues


def find_duplicates(db: Session) -> list[Issue]:
    """Find duplicate active claims that assert the same value for one entity.

    Args:
        db: Active synchronous database session.

    Returns:
        Open duplicate issues for claims repeated across source records.

    Raises:
        SQLAlchemyError: If claims or issues cannot be queried or persisted.
    """
    statement = (
        select(Claim, Record)
        .join(Record, Claim.record_id == Record.id)
        .where(Claim.superseded_by.is_(None), Record.superseded_by.is_(None))
    )
    groups: dict[tuple[str, str, str], list[tuple[Claim, Record]]] = defaultdict(list)
    for claim, record in db.execute(statement):
        groups[(record.entity_id, claim.attribute, _json_key(claim.value))].append((claim, record))

    now = datetime.now(UTC)
    issues: list[Issue] = []
    for (entity_id, attribute, value_key), claims in groups.items():
        sources = {claim.source_id for claim, _ in claims}
        if len(claims) < 2 or len(sources) < 2:
            continue
        claim_ids = [claim.id for claim, _ in claims]
        issues.append(
            create_issue_if_missing(
                db,
                IssueClass.DUPLICATE.value,
                claim_ids,
                now,
                {
                    "entity_id": entity_id,
                    "attribute": attribute,
                    "value_hash": value_key,
                    "claim_ids": [str(claim_id) for claim_id in claim_ids],
                    "claims": [
                        {
                            "claim_id": str(claim.id),
                            "record_id": str(claim.record_id),
                            "value": claim.value,
                            "source_id": str(claim.source_id),
                            "observed_at": to_utc(claim.observed_at).isoformat(),
                        }
                        for claim, _ in claims
                    ],
                },
            )
        )
    return issues


def find_missing(db: Session, required: dict[SourceType, list[str]]) -> list[Issue]:
    """Find active records missing fields required for their source type.

    Args:
        db: Active synchronous database session.
        required: Required payload fields per source type.

    Returns:
        Open missing-information issues for records with absent values.

    Raises:
        ValueError: If a persisted record has an unsupported source type.
        SQLAlchemyError: If records or issues cannot be queried or persisted.
    """
    records = db.scalars(select(Record).where(Record.superseded_by.is_(None))).all()
    now = datetime.now(UTC)
    issues: list[Issue] = []
    for record in records:
        source = SourceType(record.source_type)
        missing = [
            field
            for field in required.get(source, [])
            if field not in record.normalised_payload
            or record.normalised_payload[field] is None
            or record.normalised_payload[field] == ""
        ]
        validation_errors = record.normalised_payload.get("validation_errors", [])
        if "invalid" in record.flags and validation_errors:
            missing.extend(str(error) for error in validation_errors)
        if not missing:
            continue
        claim_ids = db.scalars(select(Claim.id).where(Claim.record_id == record.id)).all()
        issues.append(
            create_issue_if_missing(
                db,
                IssueClass.MISSING.value,
                list(claim_ids),
                now,
                {
                    "record_id": str(record.id),
                    "entity_id": record.entity_id,
                    "source_type": record.source_type,
                    "missing_fields": missing,
                },
            )
        )
    return issues


def detect_all(db: Session, now: datetime) -> list[Issue]:
    """Run all evidence quality detectors for the current active records.

    Args:
        db: Active synchronous database session.
        now: Aware UTC timestamp for freshness detection.

    Returns:
        Deduplicated open staleness, conflict, duplicate, and missing issues.

    Raises:
        SQLAlchemyError: If a detector's database operations fail.
    """
    issues = find_stale(db, now)
    entity_ids = db.scalars(
        select(Record.entity_id).where(Record.superseded_by.is_(None)).distinct()
    ).all()
    for entity_id in entity_ids:
        issues.extend(find_conflicts(db, entity_id))
    issues.extend(find_duplicates(db))
    issues.extend(find_missing(db, DEFAULT_REQUIRED_FIELDS))
    unique = {issue.id: issue for issue in issues}
    return list(unique.values())
