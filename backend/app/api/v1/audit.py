"""Read-only audit history routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.deps import Actor, get_db, get_pagination, require_role
from backend.app.schemas.audit import AuditEntryOut, AuditQuery
from backend.app.schemas.common import Page, PaginationParams
from backend.app.services.api_dispatch import dispatch

router = APIRouter(prefix="/audit", tags=["audit"])
VIEWER = require_role("viewer", "analyst", "approver", "admin")


@router.get("", response_model=Page[AuditEntryOut])
def query_audit(
    pagination: Annotated[PaginationParams, Depends(get_pagination)],
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(VIEWER)],
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    actor: str | None = None,
    action: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Page[AuditEntryOut]:
    """Query append-only audit entries with filters and pagination.

    Args:
        pagination: Validated limit and offset values.
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.
        entity_type: Optional entity type filter.
        entity_id: Optional entity UUID filter.
        actor: Optional actor name filter.
        action: Optional action filter.
        since: Optional inclusive start timestamp.
        until: Optional inclusive end timestamp.

    Returns:
        A page of matching audit entries.

    Raises:
        AirPowerError: If authorization or the audit service rejects the request.
    """
    filters = AuditQuery(
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        action=action,
        since=since,
        until=until,
    )
    return dispatch(
        "backend.app.services.audit.audit_service",
        "query",
        db,
        filters=filters,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{entity}/{id}", response_model=list[AuditEntryOut])
def audit_history(
    entity: str,
    id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(VIEWER)],
) -> list[AuditEntryOut]:
    """Return audit history for one entity; audit routes are read-only.

    Args:
        entity: Entity type to query.
        id: UUID of the entity.
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.

    Returns:
        The ordered audit history.

    Raises:
        AirPowerError: If authorization or the audit service rejects the request.
    """
    return dispatch("backend.app.services.audit.audit_service", "history", db, entity, id)
