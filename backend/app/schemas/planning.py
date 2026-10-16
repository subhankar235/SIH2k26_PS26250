"""Planning, solving, and schedule response schemas."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from backend.app.core.enums import ScheduleStatus
from backend.app.schemas.common import APIModel


class ProblemIn(APIModel):
    """Describe tasks, resources, constraints, and objective weights."""

    tasks: list[dict[str, Any]]
    resources: list[dict[str, Any]]
    windows: dict[str, Any]
    precedence: list[dict[str, Any]] = Field(default_factory=list)
    policies: list[dict[str, Any]] = Field(default_factory=list)
    objectives: dict[str, float]
    forecast_id: UUID | None = None


class Assignment(APIModel):
    """Assign one task to a resource within an integer time window."""

    task_id: str
    resource_id: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_interval(self) -> Assignment:
        """Ensure an assignment ends after it starts."""
        if self.end <= self.start:
            raise ValueError("assignment end must be greater than start")
        return self


class SolveIn(APIModel):
    """Request a seeded schedule solve and optional ALNS refinement."""

    problem: ProblemIn
    use_alns: bool = False
    time_limit_s: int = Field(default=30, gt=0)
    seed: int = Field(ge=0, le=2_147_483_647)


class ScheduleOut(APIModel):
    """Return a versioned schedule and solver provenance."""

    id: UUID
    version: int = Field(ge=1)
    parent_schedule_id: UUID | None = None
    assignments: list[Assignment]
    objectives: dict[str, Any]
    solver_meta: dict[str, Any]
    status: ScheduleStatus
    problem_hash: str
    created_at: AwareDatetime


class Alternative(APIModel):
    """Describe a candidate schedule and Pareto status."""

    schedule: ScheduleOut
    pareto_optimal: bool


class AlternativesOut(APIModel):
    """Return candidate schedules and objective summaries."""

    alternatives: list[Alternative]
    objective_names: list[str]


class SolverStatus(APIModel):
    """Expose a solver completion state."""

    status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"]
