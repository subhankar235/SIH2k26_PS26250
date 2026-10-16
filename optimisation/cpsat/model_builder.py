"""Compile a normalized dispatch problem into an OR-Tools CP-SAT model."""

from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from optimisation.models.problem import Problem


@dataclass
class ModelVars:
    """Expose decision variables needed by solver objectives and decoding."""

    starts: dict[str, cp_model.IntVar]
    ends: dict[str, cp_model.IntVar]
    assigned: dict[tuple[str, str], cp_model.IntVar]
    intervals: dict[tuple[str, str], cp_model.IntervalVar]
    intervals_by_resource: dict[str, list[cp_model.IntervalVar]]


def _pairs(params: dict[str, object]) -> list[tuple[str, str]]:
    """Validate a forbidden-pair list from policy parameters."""
    raw_pairs = params.get("pairs", [])
    if not isinstance(raw_pairs, list):
        raise ValueError("forbidden_pairs policy 'pairs' must be a list")
    pairs: list[tuple[str, str]] = []
    for pair in raw_pairs:
        if (
            not isinstance(pair, (list, tuple))
            or len(pair) != 2
            or not all(isinstance(item, str) for item in pair)
        ):
            raise ValueError("forbidden_pairs entries must contain two task ids")
        pairs.append((pair[0], pair[1]))
    return pairs


def build(problem: Problem) -> tuple[cp_model.CpModel, ModelVars]:
    """Create exactly-once task assignments with capacity, window, and precedence rules.

    Args:
        problem: Fully normalized immutable scheduling problem.

    Returns:
        CP-SAT model and all named variables used by objective solving and decoding.

    Raises:
        ValueError: If the problem contains duplicate ids or malformed policies.
    """
    if problem.horizon <= 0:
        raise ValueError("problem horizon must be positive")
    if len({task.id for task in problem.tasks}) != len(problem.tasks):
        raise ValueError("task ids must be unique")
    if len({resource.id for resource in problem.resources}) != len(problem.resources):
        raise ValueError("resource ids must be unique")

    model = cp_model.CpModel()
    starts: dict[str, cp_model.IntVar] = {}
    ends: dict[str, cp_model.IntVar] = {}
    assigned: dict[tuple[str, str], cp_model.IntVar] = {}
    intervals: dict[tuple[str, str], cp_model.IntervalVar] = {}
    intervals_by_resource: dict[str, list[cp_model.IntervalVar]] = {
        resource.id: [] for resource in problem.resources
    }

    tasks_by_id = {task.id: task for task in problem.tasks}
    for task in problem.tasks:
        earliest_start = max(0, task.earliest)
        latest_start = min(task.latest, problem.horizon - task.duration)
        start = model.new_int_var(
            earliest_start, max(earliest_start, latest_start), f"start_{task.id}"
        )
        end = model.new_int_var(0, problem.horizon, f"end_{task.id}")
        starts[task.id] = start
        ends[task.id] = end
        model.add(end == start + task.duration)
        model.add(end <= problem.horizon)
        if latest_start < earliest_start:
            model.add_bool_or([])

        choices: list[cp_model.IntVar] = []
        for resource in problem.resources:
            if task.resource_type not in {"*", "any"} and task.resource_type != resource.type:
                continue
            assignment = model.new_bool_var(f"assign_{task.id}_{resource.id}")
            assigned[(task.id, resource.id)] = assignment
            choices.append(assignment)
            optional_interval = model.new_optional_interval_var(
                start,
                task.duration,
                end,
                assignment,
                f"interval_{task.id}_{resource.id}",
            )
            intervals[(task.id, resource.id)] = optional_interval
            intervals_by_resource[resource.id].append(optional_interval)

            window_choices: list[cp_model.IntVar] = []
            for window_index, (window_start, window_end) in enumerate(resource.available):
                window_choice = model.new_bool_var(f"window_{task.id}_{resource.id}_{window_index}")
                window_choices.append(window_choice)
                model.add(start >= window_start).only_enforce_if(window_choice)
                model.add(end <= window_end).only_enforce_if(window_choice)
            model.add(sum(window_choices) == assignment)
        model.add(sum(choices) == 1)

    for precedence in problem.precedence:
        if precedence.before not in tasks_by_id or precedence.after not in tasks_by_id:
            raise ValueError("precedence references an unknown task")
        model.add(starts[precedence.after] >= ends[precedence.before] + precedence.min_gap)

    for resource in problem.resources:
        if resource.capacity < 1:
            raise ValueError(f"resource {resource.id!r} capacity must be positive")
        if intervals_by_resource[resource.id]:
            model.add_cumulative(
                intervals_by_resource[resource.id],
                [1] * len(intervals_by_resource[resource.id]),
                resource.capacity,
            )

    for policy in problem.policies:
        if policy.name == "fixed_assignments":
            fixed = policy.params.get("assignments", [])
            if not isinstance(fixed, list):
                raise ValueError("fixed_assignments policy requires an assignment list")
            for item in fixed:
                if not isinstance(item, dict):
                    raise ValueError("fixed assignment entries must be objects")
                task_id = str(item.get("task_id", ""))
                resource_id = str(item.get("resource_id", ""))
                fixed_assignment = assigned.get((task_id, resource_id))
                if fixed_assignment is None or task_id not in starts:
                    model.add_bool_or([])
                    continue
                model.add(fixed_assignment == 1)
                model.add(starts[task_id] == int(item["start"]))
                model.add(ends[task_id] == int(item["end"]))
        elif policy.name in {"forbidden_pairs", "no_overlap"}:
            pairs = _pairs(policy.params) if policy.name == "forbidden_pairs" else []
            if policy.name == "no_overlap":
                ids = policy.params.get("task_ids", [])
                if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
                    raise ValueError("no_overlap policy 'task_ids' must be a string list")
                pairs = [
                    (ids[left], ids[right])
                    for left in range(len(ids))
                    for right in range(left + 1, len(ids))
                ]
            for left_id, right_id in pairs:
                if left_id not in tasks_by_id or right_id not in tasks_by_id:
                    raise ValueError("no-overlap policy references an unknown task")
                for resource in problem.resources:
                    left = intervals.get((left_id, resource.id))
                    right = intervals.get((right_id, resource.id))
                    if left is not None and right is not None:
                        model.add_no_overlap([left, right])
        elif policy.name == "max_total_hours":
            maximum = policy.params.get("hours")
            if not isinstance(maximum, int) or maximum < 0:
                raise ValueError("max_total_hours policy requires non-negative integer hours")
            for resource in problem.resources:
                model.add(
                    sum(
                        tasks_by_id[task.id].duration * assigned[(task.id, resource.id)]
                        for task in problem.tasks
                        if (task.id, resource.id) in assigned
                    )
                    <= maximum
                )
        else:
            raise ValueError(f"unsupported policy {policy.name!r}")

    return model, ModelVars(starts, ends, assigned, intervals, intervals_by_resource)
