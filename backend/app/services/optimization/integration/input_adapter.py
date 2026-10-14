"""Convert validated planning request data into immutable solver inputs."""

from __future__ import annotations

from typing import Any

from backend.app.services.optimization.models.problem import Problem, problem_from_mapping


def to_problem(data: dict[str, Any]) -> Problem:
    """Build a solver problem from a JSON-compatible planning request."""
    return problem_from_mapping(data)
