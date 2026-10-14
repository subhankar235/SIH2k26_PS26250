"""Thin independent verification routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.deps import Actor, get_db, require_role
from backend.app.schemas.verification import VerificationOut, VerifyIn
from backend.app.services.api_dispatch import dispatch

router = APIRouter(prefix="/verification", tags=["verification"])
VIEWER = require_role("viewer", "analyst", "approver", "admin")


@router.post("/check", response_model=VerificationOut)
def run_checks(
    request: VerifyIn,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[Actor, Depends(require_role("analyst", "admin"))],
) -> VerificationOut:
    """Run independent checks for a target.

    Args:
        request: Target type and UUID to verify.
        db: Request-scoped database session.
        actor: Authenticated analyst.

    Returns:
        The authoritative verification result.

    Raises:
        AirPowerError: If authorization or the verification service rejects the request.
    """
    return dispatch(
        "backend.app.services.verification.verification_service",
        "run_checks",
        db,
        request.target_type,
        request.target_id,
        actor.id,
    )


@router.get("/{id}", response_model=VerificationOut)
def get_verification(
    id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(VIEWER)],
) -> VerificationOut:
    """Return a saved verification result.

    Args:
        id: UUID of the verification result.
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.

    Returns:
        The saved verification result.

    Raises:
        AirPowerError: If authorization or the verification service rejects the request.
    """
    return dispatch("backend.app.services.verification.verification_service", "get", db, id)
