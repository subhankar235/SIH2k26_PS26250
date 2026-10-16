"""Solve discrete resource schedules with OR-Tools CP-SAT."""

from __future__ import annotations

from time import monotonic
from typing import Literal

from ortools.sat.python import cp_model

from optimisation.cpsat.model_builder import ModelVars, build
from optimisation.models.problem import Problem
from optimisation.models.solution import Assignment, Solution

_OBJECTIVES = {"makespan", "cost", "lateness", "priority_completion"}
_OBJECTIVE_SCALE = 1000


def _objective_weight(problem: Problem, name: str) -> int:
    """Convert a user objective weight into a stable integer CP-SAT coefficient."""
    default = 1.0 if name == "makespan" and not problem.objectives else 0.0
    value = problem.objectives.get(name, default)
    if value < 0:
        raise ValueError(f"objective weight {name!r} must be non-negative")
    return round(value * _OBJECTIVE_SCALE)


def _add_objective(model: cp_model.CpModel, variables: ModelVars, problem: Problem) -> None:
    """Minimize weighted makespan, operating cost, lateness, and priority completion."""
    unsupported = set(problem.objectives) - _OBJECTIVES
    if unsupported:
        raise ValueError(f"unsupported objective weights: {sorted(unsupported)}")
    if any(weight < 0 for weight in problem.objectives.values()):
        raise ValueError("objective weights must be non-negative")

    makespan = model.new_int_var(0, problem.horizon, "makespan")
    if problem.tasks:
        model.add_max_equality(makespan, [variables.ends[task.id] for task in problem.tasks])
    else:
        model.add(makespan == 0)
    terms: list[cp_model.LinearExpr] = []

    makespan_weight = _objective_weight(problem, "makespan")
    if makespan_weight:
        terms.append(makespan_weight * makespan)

    cost_weight = _objective_weight(problem, "cost")
    if cost_weight:
        resources = {resource.id: resource for resource in problem.resources}
        for task in problem.tasks:
            for resource_id, resource in resources.items():
                assignment = variables.assigned.get((task.id, resource_id))
                if assignment is None:
                    continue
                cost = round(resource.cost_per_unit * task.duration * _OBJECTIVE_SCALE)
                if cost:
                    terms.append(cost_weight * cost * assignment)

    lateness_weight = _objective_weight(problem, "lateness")
    priority_weight = _objective_weight(problem, "priority_completion")
    for task in problem.tasks:
        if lateness_weight and task.due is not None:
            lateness = model.new_int_var(0, problem.horizon, f"lateness_{task.id}")
            assert task.due is not None
            model.add(lateness >= variables.ends[task.id] - task.due)
            terms.append(lateness_weight * lateness)
        if priority_weight and task.priority:
            terms.append(priority_weight * task.priority * variables.ends[task.id])

    if not terms:
        # Empty weights and zero explicit weights still produce a deterministic useful plan.
        terms.append(makespan)
    model.minimize(sum(terms))


def _apply_hint(
    model: cp_model.CpModel,
    variables: ModelVars,
    problem: Problem,
    hint: Solution | None,
) -> None:
    """Seed CP-SAT search with any still-valid assignments from an earlier solution."""
    if hint is None:
        return
    task_by_id = {task.id: task for task in problem.tasks}
    hinted = {item.task_id: item for item in hint.assignments if item.task_id in task_by_id}
    for task in problem.tasks:
        assignment = hinted.get(task.id)
        if assignment is None:
            continue
        model.add_hint(variables.starts[task.id], assignment.start)
        for resource in problem.resources:
            variable = variables.assigned.get((task.id, resource.id))
            if variable is not None:
                model.add_hint(variable, int(resource.id == assignment.resource_id))


def _metrics(problem: Problem, assignments: list[Assignment]) -> dict[str, float]:
    """Calculate schedule objective metrics from the decoded assignments."""
    if not assignments:
        return {"makespan": 0.0, "cost": 0.0, "lateness": 0.0, "priority_completion": 0.0}
    tasks = {task.id: task for task in problem.tasks}
    resources = {resource.id: resource for resource in problem.resources}
    makespan = max(assignment.end for assignment in assignments)
    cost = sum(
        (assignment.end - assignment.start) * resources[assignment.resource_id].cost_per_unit
        for assignment in assignments
    )
    lateness = 0
    for assignment in assignments:
        due = tasks[assignment.task_id].due
        if due is not None:
            lateness += max(0, assignment.end - due)
    priority_completion = sum(
        tasks[assignment.task_id].priority * assignment.end for assignment in assignments
    )
    return {
        "makespan": float(makespan),
        "cost": float(cost),
        "lateness": float(lateness),
        "priority_completion": float(priority_completion),
    }


def solve(
    problem: Problem,
    time_limit_s: int,
    seed: int,
    hint: Solution | None = None,
) -> Solution:
    """Find a feasible schedule using deterministic single-worker CP-SAT search.

    Args:
        problem: Normalized dispatch problem.
        time_limit_s: Positive solver wall-clock limit.
        seed: CP-SAT random seed.
        hint: Optional prior solution used as a search hint.

    Returns:
        Feasible or optimal assignments; infeasible/unknown are represented by status.

    Raises:
        ValueError: If solver options or model configuration are invalid.
    """
    if time_limit_s < 1:
        raise ValueError("time_limit_s must be positive")
    if not 0 <= seed <= 2_147_483_647:
        raise ValueError("seed must be in [0, 2147483647]")
    model, variables = build(problem)
    _add_objective(model, variables, problem)
    _apply_hint(model, variables, problem, hint)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_s)
    solver.parameters.random_seed = int(seed)
    solver.parameters.num_search_workers = 1
    started = monotonic()
    status = solver.solve(model)
    elapsed = monotonic() - started
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        label: Literal["INFEASIBLE", "UNKNOWN"] = (
            "INFEASIBLE" if status == cp_model.INFEASIBLE else "UNKNOWN"
        )
        return Solution(
            assignments=[],
            objectives={},
            status=label,
            wall_time_s=elapsed,
            seed=seed,
            metadata={
                "solver_status": solver.status_name(status),
                "wall_time_s": elapsed,
                "branches": solver.num_branches,
                "conflicts": solver.num_conflicts,
            },
        )

    resource_by_task: dict[str, str] = {}
    for task in problem.tasks:
        selected = [
            resource.id
            for resource in problem.resources
            if (task.id, resource.id) in variables.assigned
            and solver.boolean_value(variables.assigned[(task.id, resource.id)])
        ]
        if len(selected) != 1:
            raise RuntimeError(f"CP-SAT returned {len(selected)} resources for task {task.id!r}")
        resource_by_task[task.id] = selected[0]
    assignments = [
        Assignment(
            task_id=task.id,
            resource_id=resource_by_task[task.id],
            start=solver.value(variables.starts[task.id]),
            end=solver.value(variables.ends[task.id]),
        )
        for task in problem.tasks
    ]
    return Solution(
        assignments=assignments,
        objectives=_metrics(problem, assignments),
        status="OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
        wall_time_s=elapsed,
        seed=seed,
        metadata={
            "solver_status": solver.status_name(status),
            "objective_value": solver.objective_value,
            "best_objective_bound": solver.best_objective_bound,
            "wall_time_s": elapsed,
            "branches": solver.num_branches,
            "conflicts": solver.num_conflicts,
        },
    )
