"""Thin schedule replanning and diff routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.deps import Actor, get_db, get_idempotency_key, require_role
from backend.app.schemas.replanning import ReplanIn, ReplanOut, ScheduleDiff
from backend.app.services.api_dispatch import dispatch
from backend.app.services.idempotency import execute_idempotently

router = APIRouter(prefix="/replanning", tags=["replanning"])
VIEWER = require_role("viewer", "analyst", "approver", "admin")


@router.post("/run", response_model=ReplanOut)
def replan(
    request: ReplanIn,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[Actor, Depends(require_role("analyst", "admin"))],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> ReplanOut:
    """Replan a schedule after input changes.

    Args:
        request: Schedule id and changed inputs.
        db: Request-scoped database session.
        actor: Authenticated analyst.
        idempotency_key: Optional key for replay-safe replanning.

    Returns:
        The new schedule and its diff.

    Raises:
        AirPowerError: If authorization or the replanning service rejects the request.
    """
    return execute_idempotently(
        db,
        idempotency_key,
        request.model_dump(mode="json"),
        lambda: dispatch(
            "backend.app.services.replanning.incremental_recompute",
            "replan",
            db,
            request.schedule_id,
            request.changes,
            actor.id,
        ),
        result_model=ReplanOut,
    )


@router.get("/diff/{old}/{new}", response_model=ScheduleDiff)
def diff_schedules(
    old: UUID,
    new: UUID,
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(VIEWER)],
) -> ScheduleDiff:
    """Compare two persisted schedule versions.

    Args:
        old: UUID of the earlier schedule.
        new: UUID of the later schedule.
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.

    Returns:
        Added, removed, moved, and unchanged assignments.

    Raises:
        AirPowerError: If authorization or the replanning service rejects the request.
    """
    return dispatch(
        "backend.app.services.replanning.schedule_diff",
        "diff_by_id",
        db,
        old,
        new,
    )
