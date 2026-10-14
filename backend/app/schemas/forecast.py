"""Forecasting requests and versioned forecast responses."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from backend.app.schemas.common import APIModel


class ForecastIn(APIModel):
    """Request a seeded forecast for a target and horizon."""

    target: str = Field(min_length=1)
    horizon: int = Field(gt=0)
    seed: int


class ForecastPoint(APIModel):
    """Represent one forecast point and its prediction interval."""

    t: AwareDatetime
    mean: float
    lower: float
    upper: float

    @model_validator(mode="after")
    def validate_interval(self) -> ForecastPoint:
        """Ensure the lower bound does not exceed the upper bound."""
        if self.lower > self.upper:
            raise ValueError("lower must not exceed upper")
        return self


class ForecastOut(APIModel):
    """Return a persisted forecast and its source-version metadata."""

    id: UUID
    target: str
    horizon: int
    points: list[ForecastPoint]
    calibration_meta: dict[str, Any]
    input_versions: dict[str, Any]
    version: int = Field(ge=1)
    high_uncertainty: bool
