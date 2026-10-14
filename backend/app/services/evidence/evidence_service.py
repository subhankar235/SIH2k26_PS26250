"""Read-oriented evidence service entry points used by the API."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models.claim import Issue
from backend.app.schemas.common import Page
from backend.app.schemas.evidence import IssueOut
from backend.app.services.ingestion.normaliser import to_utc


def list_issues(
    db: Session,
    limit: int,
    offset: int,
    issue_class: str | None = None,
) -> Page[IssueOut]:
    """Return a filtered page of evidence issues.

    Args:
        db: Active synchronous database session.
        limit: Maximum number of issues to return.
        offset: Number of matching issues to skip.
        issue_class: Optional issue category filter.

    Returns:
        A page with total matching issue count and issue responses.

    Raises:
        ValueError: If limit or offset is invalid.
    """
    if limit < 1 or offset < 0:
        raise ValueError("limit must be positive and offset must not be negative")
    filters = []
    if issue_class is not None:
        filters.append(Issue.issue_class == issue_class)
    total = db.scalar(select(func.count()).select_from(Issue).where(*filters)) or 0
    issues = db.scalars(
        select(Issue)
        .where(*filters)
        .order_by(Issue.detected_at.desc(), Issue.id)
        .limit(limit)
        .offset(offset)
    ).all()
    items = [
        IssueOut(
            id=issue.id,
            issue_class=issue.issue_class,
            claim_ids=issue.claim_ids,
            detected_at=to_utc(issue.detected_at),
            status=issue.status,
            details=issue.details,
        )
        for issue in issues
    ]
    return Page[IssueOut](items=items, total=total, limit=limit, offset=offset)
