"""Health check endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.core.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    """Return application and database liveness.

    Args:
        db: Database session supplied by the request dependency.

    Returns:
        A status object indicating application and database health.
    """
    result = db.execute(text("SELECT 1"))
    result.scalar_one()
    return {"status": "ok", "db": "ok"}
