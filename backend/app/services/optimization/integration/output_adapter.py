"""Convert solver results into the existing schedule persistence payload."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from backend.app.services.optimization.models.problem import Problem
from backend.app.services.optimization.models.solution import Solution


def to_schedule_values(
    problem: Problem,
    solution: Solution,
    *,
    time_limit_s: int,
    parent_schedule_id: UUID | None = None,
) -> dict[str, Any]:
    """Produce Schedule column values while retaining solver provenance."""
    canonical = {
        "tasks": [task.__dict__ for task in sorted(problem.tasks, key=lambda item: item.task_id)],
        "resources": [
            {**resource.__dict__, "availability": list(resource.availability)}
            for resource in sorted(problem.resources, key=lambda item: item.resource_id)
        ],
        "precedence": [
            item.__dict__
            for item in sorted(
                problem.precedence,
                key=lambda item: (item.before_task_id, item.after_task_id, item.min_lag),
            )
        ],
        "policies": [
            {"name": item.name, "parameters": item.parameters}
            for item in sorted(
                problem.policies,
                key=lambda item: (
                    item.name,
                    json.dumps(item.parameters, sort_keys=True, separators=(",", ":")),
                ),
            )
        ],
        "horizon_start": problem.horizon_start,
        "horizon_end": problem.horizon_end,
        "objectives": problem.objectives,
    }
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False)
    problem_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return {
        "parent_schedule_id": parent_schedule_id,
        "assignments": [
            {
                "task_id": assignment.task_id,
                "resource_id": assignment.resource_id,
                "start": assignment.start,
                "end": assignment.end,
            }
            for assignment in solution.assignments
        ],
        "objectives": solution.objectives,
        "solver_meta": {
            "solver_status": solution.status,
            "execution_time_s": solution.wall_time_s,
            "random_seed": solution.seed,
            "solver_configuration": {"time_limit_s": time_limit_s},
            "problem_hash": problem_hash,
            "input_versions": {},
            "input_provenance": (
                "ProblemIn contains no Record IDs or input versions; none were inferred"
            ),
            "forecast_uncertainty": {
                "applied": False,
                "reason": "ProblemIn contains no forecast reference",
            },
            "problem_snapshot": canonical,
        },
        "status": "draft",
        "problem_hash": problem_hash,
    }
