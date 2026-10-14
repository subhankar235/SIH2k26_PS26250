"""Thin agent workflow and explanation routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.core.deps import Actor, get_db, get_idempotency_key, require_role
from backend.app.schemas.agents import AgentRequestIn, AgentRunOut, ExplanationOut
from backend.app.services.api_dispatch import dispatch
from backend.app.services.idempotency import execute_idempotently

router = APIRouter(prefix="/agents", tags=["agents"])
VIEWER = require_role("viewer", "analyst", "approver", "admin")


@router.post("/requests", response_model=AgentRunOut, status_code=status.HTTP_202_ACCEPTED)
def start_run(
    request: AgentRequestIn,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[Actor, Depends(require_role("analyst", "admin"))],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> AgentRunOut:
    """Start an agent workflow and return a pollable run id.

    Args:
        request: Structured agent task request and seed.
        db: Request-scoped database session.
        actor: Authenticated analyst.
        idempotency_key: Optional key for replay-safe workflow creation.

    Returns:
        The initial agent-run state.

    Raises:
        AirPowerError: If authorization or the agent service rejects the request.
    """
    return execute_idempotently(
        db,
        idempotency_key,
        request.model_dump(mode="json"),
        lambda: dispatch(
            "backend.app.services.agent_service",
            "start",
            db,
            request,
            actor=actor.id,
        ),
        result_model=AgentRunOut,
    )


@router.get("/requests/{id}", response_model=AgentRunOut)
def get_run(
    id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(VIEWER)],
) -> AgentRunOut:
    """Return current agent workflow progress.

    Args:
        id: UUID of the agent run.
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.

    Returns:
        Current agent state and workflow steps.

    Raises:
        AirPowerError: If authorization or the agent service rejects the request.
    """
    return dispatch("backend.app.services.agent_service", "get", db, id)


@router.get("/requests/{id}/explanation", response_model=ExplanationOut)
def get_explanation(
    id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(VIEWER)],
) -> ExplanationOut:
    """Return a citation-validated explanation for an agent run.

    Args:
        id: UUID of the agent run.
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.

    Returns:
        Explanation text and resolved evidence citations.

    Raises:
        AirPowerError: If authorization or the explanation service rejects the request.
    """
    return dispatch("backend.app.services.explanation.explainer", "get_explanation", db, id)
