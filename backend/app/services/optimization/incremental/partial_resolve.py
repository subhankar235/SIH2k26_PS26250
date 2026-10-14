"""Re-solve an updated problem using a compatible previous solution as a hint."""

from __future__ import annotations

from backend.app.services.optimization.cpsat.solver import solve
from backend.app.services.optimization.models.problem import Problem
from backend.app.services.optimization.models.solution import Solution


def partial_resolve(
    problem: Problem,
    previous_solution: Solution | None,
    affected_task_ids: set[str],
    *,
    time_limit_s: int,
    seed: int,
) -> Solution:
    """Solve the full updated model while hinting compatible unaffected tasks.

    Removed tasks, changed-duration tasks, and assignments to newly unavailable
    resources are omitted from hints. If no compatible previous result is
    available, this is the normal full-solve path.
    """
    return solve(
        problem,
        time_limit_s=time_limit_s,
        seed=seed,
        previous_solution=previous_solution,
        affected_task_ids=affected_task_ids,
    )
