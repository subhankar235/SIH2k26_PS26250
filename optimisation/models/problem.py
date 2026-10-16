"""Immutable time-indexed dispatch problem models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Task:
    """One indivisible task with duration and a start-time window."""

    id: str
    duration: int
    resource_type: str
    earliest: int
    latest: int
    priority: int = 1
    due: int | None = None


@dataclass(frozen=True)
class Resource:
    """A resource with capacity and availability time windows."""

    id: str
    type: str
    capacity: int
    available: list[tuple[int, int]]
    cost_per_unit: float = 0.0


@dataclass(frozen=True)
class Precedence:
    """Require one task to finish before another may start."""

    before: str
    after: str
    min_gap: int = 0


@dataclass(frozen=True)
class Policy:
    """Named scheduling policy and its serializable parameters."""

    name: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Problem:
    """Complete deterministic scheduling problem and input provenance."""

    tasks: list[Task]
    resources: list[Resource]
    precedence: list[Precedence]
    policies: list[Policy]
    horizon: int
    objectives: dict[str, float]
    input_versions: list[dict[str, Any]] = field(default_factory=list)
    forecast_meta: dict[str, Any] = field(default_factory=dict)
