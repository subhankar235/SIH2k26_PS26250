"""Seeded destroy-and-repair large-neighborhood search for schedules."""

from __future__ import annotations

from dataclasses import replace
from time import monotonic

import numpy as np

from optimisation.cpsat.solver import solve
from optimisation.models.problem import Policy, Problem
from optimisation.models.solution import Solution


def _score(problem: Problem, solution: Solution) -> float:
    """Calculate the weighted objective value of a feasible solution."""
    weights = problem.objectives or {"makespan": 1.0}
    return sum(weights.get(name, 0.0) * value for name, value in solution.objectives.items())


def improve(
    problem: Problem,
    initial: Solution,
    iterations: int,
    time_limit_s: int,
    seed: int,
) -> Solution:
    """Improve a CP-SAT incumbent using seeded destroy-and-repair neighborhoods.

    Each iteration destroys a reproducibly selected subset of task assignments and
    repairs the remaining neighborhood with CP-SAT while freezing the others.

    Args:
        problem: Normalized scheduling problem.
        initial: Feasible incumbent produced by the primary CP-SAT solve.
        iterations: Maximum destroy-and-repair iterations.
        time_limit_s: Total wall-clock budget for improvement.
        seed: Seed for a local NumPy generator and each CP-SAT repair call.

    Returns:
        Best feasible solution found; never worse than ``initial`` by weighted objectives.

    Raises:
        ValueError: If iterations or time_limit_s are invalid.
    """
    if iterations < 0 or time_limit_s < 1:
        raise ValueError("iterations must be non-negative and time_limit_s positive")
    if initial.status not in {"OPTIMAL", "FEASIBLE"}:
        return initial
    if iterations == 0 or not initial.assignments:
        return initial

    rng = np.random.default_rng(seed)
    task_ids = sorted(task.id for task in problem.tasks)
    current = initial
    best = initial
    best_score = _score(problem, best)
    deadline = monotonic() + time_limit_s

    for iteration in range(iterations):
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        destroy_count = max(1, min(len(task_ids), int(np.ceil(len(task_ids) * 0.25))))
        destroyed = set(rng.choice(task_ids, size=destroy_count, replace=False).tolist())
        fixed = [
            {
                "task_id": assignment.task_id,
                "resource_id": assignment.resource_id,
                "start": assignment.start,
                "end": assignment.end,
            }
            for assignment in current.assignments
            if assignment.task_id not in destroyed
        ]
        neighborhood = replace(
            problem,
            policies=[*problem.policies, Policy("fixed_assignments", {"assignments": fixed})],
        )
        repair_limit = max(1, min(time_limit_s, int(np.ceil(remaining))))
        candidate = solve(
            neighborhood,
            time_limit_s=repair_limit,
            seed=seed + iteration + 1,
            hint=current,
        )
        if candidate.status not in {"OPTIMAL", "FEASIBLE"}:
            continue
        score = _score(problem, candidate)
        if score < best_score:
            best = candidate
            best_score = score
        current = candidate if score <= _score(problem, current) else best
    return best
