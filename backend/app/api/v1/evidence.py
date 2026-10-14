"""Thin evidence issue and provenance routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.core.deps import Actor, get_db, get_pagination, require_role
from backend.app.schemas.common import Page, PaginationParams
from backend.app.schemas.evidence import AutopsyOut, IssueOut, ProvenanceStep
from backend.app.services.api_dispatch import dispatch

router = APIRouter(prefix="/evidence", tags=["evidence"])
VIEWER = require_role("viewer", "analyst", "approver", "admin")


@router.get("/issues", response_model=Page[IssueOut])
def list_issues(
    pagination: Annotated[PaginationParams, Depends(get_pagination)],
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(VIEWER)],
    issue_class: Annotated[str | None, Query()] = None,
) -> Page[IssueOut]:
    """List evidence issues with optional issue-class filtering.

    Args:
        pagination: Validated limit and offset values.
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.
        issue_class: Optional issue-class filter.

    Returns:
        A page of matching issues.

    Raises:
        AirPowerError: If authorization or the evidence service rejects the request.
    """
    return dispatch(
        "backend.app.services.evidence.evidence_service",
        "list_issues",
        db,
        limit=pagination.limit,
        offset=pagination.offset,
        issue_class=issue_class,
    )


@router.get("/issues/{id}/autopsy", response_model=AutopsyOut)
def build_autopsy(
    id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(VIEWER)],
) -> AutopsyOut:
    """Return an evidence autopsy for one issue.

    Args:
        id: UUID of the issue to analyze.
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.

    Returns:
        The issue autopsy.

    Raises:
        AirPowerError: If authorization or the evidence service rejects the request.
    """
    return dispatch("backend.app.services.evidence.autopsy", "build_autopsy", db, id)


@router.get("/provenance/{record_id}", response_model=list[ProvenanceStep])
def trace_provenance(
    record_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(VIEWER)],
) -> list[ProvenanceStep]:
    """Trace the provenance of one normalized record.

    Args:
        record_id: UUID of the record to trace.
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.

    Returns:
        Ordered provenance steps.

    Raises:
        AirPowerError: If authorization or the evidence service rejects the request.
    """
    return dispatch("backend.app.services.evidence.provenance_tracer", "trace", db, record_id)
