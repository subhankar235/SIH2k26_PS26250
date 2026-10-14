"""Thin ingestion API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.core.deps import (
    Actor,
    get_db,
    get_idempotency_key,
    get_pagination,
    require_role,
)
from backend.app.schemas.common import Page, PaginationParams
from backend.app.schemas.ingestion import (
    FlaggedRecordOut,
    IngestEventIn,
    IngestStatusOut,
    RecordOut,
)
from backend.app.services.api_dispatch import dispatch
from backend.app.services.idempotency import execute_idempotently

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/events", response_model=RecordOut, status_code=status.HTTP_202_ACCEPTED)
def ingest_event(
    request: IngestEventIn,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[Actor, Depends(require_role("analyst"))],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> RecordOut:
    """Accept one source event for ingestion.

    Args:
        request: Validated synthetic source event.
        db: Request-scoped database session.
        actor: Authenticated analyst.
        idempotency_key: Optional key for replay-safe event creation.

    Returns:
        The normalized record response.

    Raises:
        AirPowerError: If authorization or the ingestion service rejects the request.
    """
    return execute_idempotently(
        db,
        idempotency_key,
        request.model_dump(mode="json"),
        lambda: dispatch(
            "backend.app.services.ingestion.ingestion_service",
            "ingest_event",
            db,
            source=request.source,
            source_event_id=request.source_event_id,
            event_time=request.event_time,
            payload=request.payload,
        ),
        result_model=RecordOut,
    )


@router.get("/status", response_model=IngestStatusOut)
def get_status(
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(require_role("viewer", "analyst", "approver", "admin"))],
) -> IngestStatusOut:
    """Return health information for ingestion topics.

    Args:
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.

    Returns:
        Per-topic ingestion status.

    Raises:
        AirPowerError: If authorization or the ingestion service rejects the request.
    """
    return dispatch("backend.app.services.ingestion.ingestion_service", "get_status", db)


@router.get("/flagged", response_model=Page[FlaggedRecordOut])
def list_flagged(
    pagination: Annotated[PaginationParams, Depends(get_pagination)],
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(require_role("viewer", "analyst", "approver", "admin"))],
) -> Page[FlaggedRecordOut]:
    """Return flagged records using shared pagination parameters.

    Args:
        pagination: Validated limit and offset values.
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.

    Returns:
        A page of flagged records.

    Raises:
        AirPowerError: If authorization or the ingestion service rejects the request.
    """
    return dispatch(
        "backend.app.services.ingestion.ingestion_service",
        "list_flagged",
        db,
        limit=pagination.limit,
        offset=pagination.offset,
    )
