"""Benchmark and ablation result schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from backend.app.schemas.common import APIModel


class BenchmarkResultOut(APIModel):
    """Return a benchmark metric and its experiment metadata."""

    id: UUID
    experiment_id: UUID
    scenario: str
    seed: int
    metrics: dict[str, float]
    metadata: dict[str, Any] = Field(default_factory=dict)


class AblationOut(APIModel):
    """Compare a system ablation against its baseline."""

    name: str
    baseline_metrics: dict[str, float]
    ablation_metrics: dict[str, float]
    delta: dict[str, float]


class StatResult(APIModel):
    """Report an effect size, confidence interval, and p-value."""

    effect_size: float
    ci_low: float
    ci_high: float
    p_value: float = Field(ge=0, le=1)
