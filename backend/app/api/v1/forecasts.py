"""Thin forecast creation and retrieval routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.deps import Actor, get_db, get_idempotency_key, require_role
from backend.app.schemas.forecast import ForecastIn, ForecastOut
from backend.app.services.api_dispatch import dispatch
from backend.app.services.idempotency import execute_idempotently

router = APIRouter(prefix="/forecasts", tags=["forecasts"])
VIEWER = require_role("viewer", "analyst", "approver", "admin")


@router.post("", response_model=ForecastOut)
def create_forecast(
    request: ForecastIn,
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(require_role("analyst", "admin"))],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
) -> ForecastOut:
    """Create a seeded forecast and replay matching idempotent requests.

    Args:
        request: Forecast target, horizon, and deterministic seed.
        db: Request-scoped database session.
        _actor: Authenticated analyst.
        idempotency_key: Optional key for replay-safe forecast creation.

    Returns:
        The persisted forecast response.

    Raises:
        AirPowerError: If authorization or the forecasting service rejects the request.
    """
    return execute_idempotently(
        db,
        idempotency_key,
        request.model_dump(mode="json"),
        lambda: dispatch(
            "backend.app.services.forecasting.predictor",
            "create_forecast",
            db,
            target=request.target,
            horizon=request.horizon,
            seed=request.seed,
        ),
        result_model=ForecastOut,
    )


@router.get("/{id}", response_model=ForecastOut)
def get_forecast(
    id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(VIEWER)],
) -> ForecastOut:
    """Return one persisted forecast.

    Args:
        id: UUID of the forecast.
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.

    Returns:
        The forecast response.

    Raises:
        AirPowerError: If authorization or the forecasting service rejects the request.
    """
    return dispatch("backend.app.services.forecasting.predictor", "get", db, id)
