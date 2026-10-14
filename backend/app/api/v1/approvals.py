"""Thin human approval queue and decision routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.deps import Actor, get_db, get_pagination, require_role
from backend.app.schemas.approvals import ApprovalDecisionIn, ApprovalOut, ApprovalQueueItem
from backend.app.schemas.common import Page, PaginationParams
from backend.app.services.api_dispatch import dispatch

router = APIRouter(prefix="/approvals", tags=["approvals"])
APPROVER = require_role("approver", "admin")


@router.get("", response_model=Page[ApprovalQueueItem])
def queue(
    pagination: Annotated[PaginationParams, Depends(get_pagination)],
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(APPROVER)],
) -> Page[ApprovalQueueItem]:
    """List targets awaiting human approval.

    Args:
        pagination: Validated limit and offset values.
        db: Request-scoped database session.
        _actor: Authenticated approver.

    Returns:
        A page of approval queue items.

    Raises:
        AirPowerError: If authorization or the approval service rejects the request.
    """
    return dispatch(
        "backend.app.services.verification.approval_router",
        "queue",
        db,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post("/{id}/decision", response_model=ApprovalOut)
def decide(
    id: UUID,
    request: ApprovalDecisionIn,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[Actor, Depends(APPROVER)],
) -> ApprovalOut:
    """Record an approval decision with required rationale.

    Args:
        id: UUID of the approval request.
        request: Decision and required rationale.
        db: Request-scoped database session.
        actor: Authenticated approver.

    Returns:
        The persisted approval decision.

    Raises:
        AirPowerError: If authorization or the approval service rejects the request.
    """
    return dispatch(
        "backend.app.services.verification.approval_router",
        "decide",
        db,
        id,
        request.decision,
        request.rationale,
        actor,
    )
