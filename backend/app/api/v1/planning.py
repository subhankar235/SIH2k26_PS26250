"""Thin schedule solve, retrieval, and alternatives routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.deps import Actor, get_db, get_idempotency_key, require_role
from backend.app.schemas.planning import AlternativesOut, ScheduleOut, SolveIn
from backend.app.services.api_dispatch import dispatch
from backend.app.services.idempotency import execute_idempotently

router = APIRouter(prefix="/planning", tags=["planning"])
VIEWER = require_role("viewer", "analyst", "approver", "admin")


@router.post("/solve", response_model=ScheduleOut)
def solve(
    request: SolveIn,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[Actor, Depends(require_role("analyst", "admin"))],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> ScheduleOut:
    """Solve and independently verify a schedule.

    Args:
        request: Problem, solver options, and deterministic seed.
        db: Request-scoped database session.
        actor: Authenticated analyst.
        idempotency_key: Optional key for replay-safe solving.

    Returns:
        The verified schedule response.

    Raises:
        AirPowerError: If authorization, solving, or verification rejects the request.
    """
    return execute_idempotently(
        db,
        idempotency_key,
        request.model_dump(mode="json"),
        lambda: dispatch(
            "backend.app.services.planning.solver_service",
            "solve_and_verify",
            db,
            request,
            actor.id,
        ),
        result_model=ScheduleOut,
    )


@router.get("/schedules/{id}", response_model=ScheduleOut)
def get_schedule(
    id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(VIEWER)],
) -> ScheduleOut:
    """Return a persisted schedule version.

    Args:
        id: UUID of the schedule.
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.

    Returns:
        The schedule response.

    Raises:
        AirPowerError: If authorization or the planning service rejects the request.
    """
    return dispatch("backend.app.services.planning.solver_service", "get_schedule", db, id)


@router.get("/alternatives", response_model=AlternativesOut)
def list_alternatives(
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(VIEWER)],
) -> AlternativesOut:
    """Return schedule alternatives with Pareto-optimal indicators.

    Args:
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.

    Returns:
        Candidate schedules and their Pareto summaries.

    Raises:
        AirPowerError: If authorization or the planning service rejects the request.
    """
    return dispatch("backend.app.services.planning.comparator", "list_alternatives", db)
