"""Solver result models shared by CP-SAT and ALNS components."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class Assignment:
    """Assign one task to a resource for a half-open integer time interval."""

    task_id: str
    resource_id: str
    start: int
    end: int


@dataclass
class Solution:
    """Represent solver status, assignments, objective metrics, and provenance."""

    assignments: list[Assignment]
    objectives: dict[str, float]
    status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"]
    wall_time_s: float
    seed: int
    metadata: dict[str, Any] = field(default_factory=dict)
