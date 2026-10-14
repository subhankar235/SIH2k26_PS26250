"""CP-SAT solver for the standalone scheduling contracts."""

from __future__ import annotations

from ortools.sat.python import cp_model

from backend.app.services.optimization.models.problem import Problem, ProblemValidationError
from backend.app.services.optimization.models.solution import Assignment, Solution


def solve(
    problem: Problem,
    *,
    time_limit_s: int,
    seed: int,
    previous_solution: Solution | None = None,
    affected_task_ids: set[str] | None = None,
) -> Solution:
    """Solve the validated integer-time problem using OR-Tools CP-SAT."""
    if time_limit_s <= 0:
        raise ProblemValidationError("time_limit_s must be positive")
    model = cp_model.CpModel()
    tasks = {task.task_id: task for task in problem.tasks}
    resources = {resource.resource_id: resource for resource in problem.resources}
    starts: dict[str, cp_model.IntVar] = {}
    ends: dict[str, cp_model.IntVar] = {}
    selected: dict[tuple[str, str], cp_model.IntVar] = {}
    window_selected: dict[tuple[str, str, int], cp_model.IntVar] = {}
    intervals_by_resource: dict[str, list[cp_model.IntervalVar]] = {
        resource.resource_id: [] for resource in problem.resources
    }
    demands_by_resource: dict[str, list[int]] = {
        resource.resource_id: [] for resource in problem.resources
    }

    for task in problem.tasks:
        start = model.new_int_var(
            task.earliest_start, task.latest_end - task.duration, f"start_{task.task_id}"
        )
        end = model.new_int_var(
            task.earliest_start + task.duration, task.latest_end, f"end_{task.task_id}"
        )
        model.add(end == start + task.duration)
        starts[task.task_id] = start
        ends[task.task_id] = end

        alternatives = []
        for resource in problem.resources:
            if (
                resource.resource_type != task.required_resource_type
                or resource.capacity < task.resource_units
            ):
                continue
            chosen = model.new_bool_var(f"assign_{task.task_id}_{resource.resource_id}")
            selected[(task.task_id, resource.resource_id)] = chosen
            alternatives.append(chosen)
            resource_intervals = []
            for interval_index, (available_start, available_end) in enumerate(
                resource.availability
            ):
                in_window = model.new_bool_var(
                    f"window_{task.task_id}_{resource.resource_id}_{interval_index}"
                )
                window_selected[(task.task_id, resource.resource_id, interval_index)] = in_window
                model.add(start >= available_start).only_enforce_if(in_window)
                model.add(end <= available_end).only_enforce_if(in_window)
                resource_intervals.append(in_window)
                interval = model.new_optional_interval_var(
                    start,
                    task.duration,
                    end,
                    in_window,
                    f"interval_{task.task_id}_{resource.resource_id}_{interval_index}",
                )
                intervals_by_resource[resource.resource_id].append(interval)
                demands_by_resource[resource.resource_id].append(task.resource_units)
            model.add(sum(resource_intervals) == chosen)
        if not alternatives:
            raise ProblemValidationError(f"task {task.task_id!r} has no eligible resource")
        model.add_exactly_one(alternatives)

    for resource in problem.resources:
        if intervals_by_resource[resource.resource_id]:
            model.add_cumulative(
                intervals_by_resource[resource.resource_id],
                demands_by_resource[resource.resource_id],
                resource.capacity,
            )

    for constraint in problem.precedence:
        model.add(
            ends[constraint.before_task_id] + constraint.min_lag <= starts[constraint.after_task_id]
        )

    if previous_solution is not None and previous_solution.usable:
        affected = affected_task_ids or set()
        for assignment in previous_solution.assignments:
            old_task = tasks.get(assignment.task_id)
            old_resource = resources.get(assignment.resource_id)
            if (
                old_task is None
                or assignment.task_id in affected
                or old_resource is None
                or old_resource.resource_type != old_task.required_resource_type
                or old_resource.capacity < old_task.resource_units
                or assignment.end - assignment.start != old_task.duration
                or assignment.start < old_task.earliest_start
                or assignment.end > old_task.latest_end
            ):
                continue
            matching_window = next(
                (
                    index
                    for index, (available_start, available_end) in enumerate(
                        old_resource.availability
                    )
                    if available_start <= assignment.start and assignment.end <= available_end
                ),
                None,
            )
            if (
                matching_window is None
                or (assignment.task_id, assignment.resource_id) not in selected
            ):
                continue
            model.add_hint(starts[assignment.task_id], assignment.start)
            model.add_hint(ends[assignment.task_id], assignment.end)
            for (task_id, resource_id), variable in selected.items():
                if task_id == assignment.task_id:
                    model.add_hint(variable, int(resource_id == assignment.resource_id))
            for (task_id, resource_id, window_index), variable in window_selected.items():
                if task_id == assignment.task_id:
                    model.add_hint(
                        variable,
                        int(
                            resource_id == assignment.resource_id
                            and window_index == matching_window
                        ),
                    )

    makespan = model.new_int_var(problem.horizon_start, problem.horizon_end, "makespan")
    model.add_max_equality(makespan, list(ends.values()))
    objective_terms = []
    if problem.objectives.get("makespan", 0.0):
        objective_terms.append(round(problem.objectives["makespan"] * 1000) * makespan)
    if problem.objectives.get("weighted_completion", 0.0):
        objective_terms.extend(
            round(problem.objectives["weighted_completion"] * 1000 * task.priority)
            * ends[task.task_id]
            for task in problem.tasks
        )
    if not objective_terms:
        raise ProblemValidationError("at least one objective weight must be non-zero")
    model.minimize(sum(objective_terms))

    for policy in problem.policies:
        maximum = policy.parameters.get("maximum")
        if policy.name == "max_makespan":
            if isinstance(maximum, bool) or not isinstance(maximum, int):
                raise ProblemValidationError(
                    "max_makespan policy requires integer parameters.maximum"
                )
            if maximum < problem.horizon_start or maximum > problem.horizon_end:
                raise ProblemValidationError("max_makespan policy is outside the planning horizon")
            model.add(makespan <= maximum)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.random_seed = seed
    solver.parameters.num_search_workers = 1
    status_code = solver.solve(model)
    status_by_code = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.UNKNOWN: "UNKNOWN",
    }
    status = status_by_code.get(status_code, "UNKNOWN")
    if status not in {"OPTIMAL", "FEASIBLE"}:
        return Solution(status, (), {}, solver.wall_time, seed)  # type: ignore[arg-type]

    assignments = []
    for task in problem.tasks:
        resource_id = next(
            resource_id
            for resource_id in resources
            if (task.task_id, resource_id) in selected
            and solver.boolean_value(selected[(task.task_id, resource_id)])
        )
        assignments.append(
            Assignment(
                task.task_id,
                resource_id,
                solver.value(starts[task.task_id]),
                solver.value(ends[task.task_id]),
            )
        )
    objective_values = {
        "makespan": float(max(item.end for item in assignments)),
        "weighted_completion": float(
            sum(tasks[item.task_id].priority * item.end for item in assignments)
        ),
    }
    return Solution(status, tuple(assignments), objective_values, solver.wall_time, seed)  # type: ignore[arg-type]
