"""Solver-neutral schedule results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SolverStatus = Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"]


@dataclass(frozen=True)
class Assignment:
    task_id: str
    resource_id: str
    start: int
    end: int


@dataclass(frozen=True)
class Solution:
    status: SolverStatus
    assignments: tuple[Assignment, ...]
    objectives: dict[str, float]
    wall_time_s: float
    seed: int

    @property
    def usable(self) -> bool:
        return self.status in {"OPTIMAL", "FEASIBLE"} and bool(self.assignments)
