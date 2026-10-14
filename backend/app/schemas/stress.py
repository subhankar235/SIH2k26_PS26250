"""Synthetic stress-run request and status schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from backend.app.schemas.common import APIModel


class StressRunIn(APIModel):
    """Start a seeded synthetic scenario with a severity level."""

    scenario: str = Field(min_length=1)
    seed: int
    severity: float = Field(ge=0, le=1)


class StressRunOut(APIModel):
    """Return stress-run status and available metrics."""

    id: UUID
    status: str
    metrics: dict[str, Any] = Field(default_factory=dict)
