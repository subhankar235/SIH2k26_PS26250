"""Thin synthetic stress-run routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from backend.app.core.deps import Actor, get_db, get_idempotency_key, require_role
from backend.app.schemas.stress import StressRunIn, StressRunOut
from backend.app.services.api_dispatch import dispatch
from backend.app.services.idempotency import execute_idempotently

router = APIRouter(prefix="/stress", tags=["stress"])
VIEWER = require_role("viewer", "analyst", "approver", "admin")


@router.post("/runs", response_model=StressRunOut, status_code=status.HTTP_202_ACCEPTED)
def start_run(
    request: StressRunIn,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[Actor, Depends(require_role("analyst", "admin"))],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> StressRunOut:
    """Enqueue a seeded stress run and return immediately.

    Args:
        request: Synthetic scenario, seed, and severity.
        db: Request-scoped database session.
        actor: Authenticated analyst.
        idempotency_key: Optional key for replay-safe run creation.

    Returns:
        A pollable stress-run response.

    Raises:
        AirPowerError: If authorization or the stress service rejects the request.
    """
    return execute_idempotently(
        db,
        idempotency_key,
        request.model_dump(mode="json"),
        lambda: dispatch(
            "backend.app.services.stress.run_manager",
            "start_run",
            db,
            request,
            actor=actor.id,
            background_tasks=background_tasks,
        ),
        result_model=StressRunOut,
    )


@router.get("/runs/{id}", response_model=StressRunOut)
def get_run(
    id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(VIEWER)],
) -> StressRunOut:
    """Return the current status for a stress run.

    Args:
        id: UUID of the stress run.
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.

    Returns:
        Current stress-run status and metrics.

    Raises:
        AirPowerError: If authorization or the stress service rejects the request.
    """
    return dispatch("backend.app.services.stress.run_manager", "get_run", db, id)
