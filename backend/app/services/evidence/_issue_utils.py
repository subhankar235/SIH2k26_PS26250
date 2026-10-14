"""Shared idempotent evidence-issue persistence helpers."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.claim import Issue
from backend.app.services.audit.audit_service import record as audit_record


def _details_hash(details: dict[str, Any]) -> str:
    """Hash JSON issue details with stable key ordering."""
    encoded = json.dumps(details, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def create_issue_if_missing(
    db: Session,
    issue_class: str,
    claim_ids: list[uuid.UUID],
    detected_at: datetime,
    details: dict[str, Any],
) -> Issue:
    """Return an existing open issue or create and audit a new one.

    Args:
        db: Active synchronous database session.
        issue_class: Issue category string value.
        claim_ids: Claims supporting the issue.
        detected_at: Aware UTC detection timestamp.
        details: Small issue details and evidence references.

    Returns:
        The existing or newly flushed open issue.
    """
    details_key = _details_hash(details)
    for existing in db.scalars(
        select(Issue).where(Issue.issue_class == issue_class, Issue.status == "open")
    ):
        if _details_hash(existing.details) == details_key:
            return existing

    issue = Issue(
        issue_class=issue_class,
        claim_ids=[str(claim_id) for claim_id in claim_ids],
        detected_at=detected_at,
        status="open",
        details=details,
    )
    db.add(issue)
    db.flush()
    audit_record(
        db,
        "issue",
        issue.id,
        "detected",
        None,
        {"issue_class": issue_class, "claim_ids": issue.claim_ids},
        "evidence_detection",
    )
    return issue
