"""Thin decision validity and reverification routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.core.deps import Actor, get_db, get_pagination, require_role
from backend.app.schemas.common import Page, PaginationParams
from backend.app.schemas.validity import DecisionOut, ReverifyIn, ReverifyOut
from backend.app.services.api_dispatch import dispatch

router = APIRouter(prefix="/validity", tags=["validity"])
VIEWER = require_role("viewer", "analyst", "approver", "admin")


@router.get("/decisions", response_model=Page[DecisionOut])
def list_decisions(
    pagination: Annotated[PaginationParams, Depends(get_pagination)],
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(VIEWER)],
    decision_status: Annotated[str | None, Query(alias="status")] = None,
) -> Page[DecisionOut]:
    """List decisions with optional validity-status filtering.

    Args:
        pagination: Validated limit and offset values.
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.
        decision_status: Optional validity status filter.

    Returns:
        A page of decisions.

    Raises:
        AirPowerError: If authorization or the validity service rejects the request.
    """
    return dispatch(
        "backend.app.services.validity.api_service",
        "list_decisions",
        db,
        limit=pagination.limit,
        offset=pagination.offset,
        status=decision_status,
    )


@router.get("/decisions/{id}", response_model=DecisionOut)
def get_decision(
    id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(VIEWER)],
) -> DecisionOut:
    """Return one decision validity envelope.

    Args:
        id: UUID of the decision.
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.

    Returns:
        The decision and its validity envelope.

    Raises:
        AirPowerError: If authorization or the validity service rejects the request.
    """
    return dispatch("backend.app.services.validity.api_service", "get_decision", db, id)


@router.post("/reverify", response_model=ReverifyOut)
def reverify(
    request: ReverifyIn,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[Actor, Depends(require_role("analyst", "admin"))],
) -> ReverifyOut:
    """Reverify decisions affected by changed inputs.

    Args:
        request: Input changes that trigger reverification.
        db: Request-scoped database session.
        actor: Authenticated analyst.

    Returns:
        The affected decisions and resulting status changes.

    Raises:
        AirPowerError: If authorization or the reverification service rejects the request.
    """
    return dispatch(
        "backend.app.services.validity.reverifier",
        "reverify",
        db,
        request.change_events,
    )
