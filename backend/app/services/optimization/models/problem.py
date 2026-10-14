"""Validated integer-time scheduling problem contracts."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any


class ProblemValidationError(ValueError):
    """Raised when a planning request cannot be represented as a valid problem."""


@dataclass(frozen=True)
class Task:
    task_id: str
    duration: int
    required_resource_type: str
    earliest_start: int
    latest_end: int
    priority: int
    resource_units: int = 1


@dataclass(frozen=True)
class Resource:
    resource_id: str
    resource_type: str
    capacity: int
    availability: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class Precedence:
    before_task_id: str
    after_task_id: str
    min_lag: int = 0


@dataclass(frozen=True)
class Policy:
    name: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class Problem:
    """A scheduling problem whose times are integer ticks in one shared unit."""

    tasks: tuple[Task, ...]
    resources: tuple[Resource, ...]
    precedence: tuple[Precedence, ...]
    policies: tuple[Policy, ...]
    horizon_start: int
    horizon_end: int
    objectives: dict[str, float]


def _required(value: dict[str, Any], key: str, context: str) -> Any:
    if key not in value or value[key] is None:
        raise ProblemValidationError(f"{context}.{key} is required")
    return value[key]


def _integer(value: Any, context: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProblemValidationError(f"{context} must be an integer optimization tick")
    if minimum is not None and value < minimum:
        raise ProblemValidationError(f"{context} must be at least {minimum}")
    return int(value)


def problem_from_mapping(data: dict[str, Any]) -> Problem:
    """Parse the explicit planning request contract without ORM dependencies."""
    windows = _required(data, "windows", "problem")
    if not isinstance(windows, dict):
        raise ProblemValidationError("problem.windows must be an object")
    if "horizon_start" in windows and "horizon_end" in windows:
        horizon_start = _integer(windows["horizon_start"], "windows.horizon_start")
        horizon_end = _integer(windows["horizon_end"], "windows.horizon_end")
    elif "start" in windows and "end" in windows:
        horizon_start = _integer(windows["start"], "windows.start")
        horizon_end = _integer(windows["end"], "windows.end")
    else:
        raise ProblemValidationError(
            "problem.windows must define integer horizon_start/horizon_end or start/end ticks"
        )
    if horizon_start < 0 or horizon_end <= horizon_start:
        raise ProblemValidationError("planning horizon must be a non-empty non-negative interval")

    raw_resources = _required(data, "resources", "problem")
    raw_tasks = _required(data, "tasks", "problem")
    if not isinstance(raw_resources, list) or not isinstance(raw_tasks, list):
        raise ProblemValidationError("problem.tasks and problem.resources must be lists")
    if not raw_resources or not raw_tasks:
        raise ProblemValidationError("problem.tasks and problem.resources must not be empty")

    resources: list[Resource] = []
    resource_ids: set[str] = set()
    for index, raw in enumerate(raw_resources):
        context = f"resources[{index}]"
        if not isinstance(raw, dict):
            raise ProblemValidationError(f"{context} must be an object")
        resource_id = str(_required(raw, "resource_id", context))
        resource_type = str(_required(raw, "resource_type", context))
        if not resource_id.strip() or not resource_type.strip():
            raise ProblemValidationError(
                f"{context}.resource_id and resource_type must not be empty"
            )
        capacity = _integer(_required(raw, "capacity", context), f"{context}.capacity", minimum=1)
        if resource_id in resource_ids:
            raise ProblemValidationError(f"duplicate resource id {resource_id!r}")
        resource_ids.add(resource_id)
        availability_data = _required(raw, "availability", context)
        if not isinstance(availability_data, list) or not availability_data:
            raise ProblemValidationError(f"{context}.availability must be a non-empty list")
        intervals: list[tuple[int, int]] = []
        for interval_index, interval in enumerate(availability_data):
            interval_context = f"{context}.availability[{interval_index}]"
            if not isinstance(interval, dict):
                raise ProblemValidationError(f"{interval_context} must be an object")
            start = _integer(
                _required(interval, "start", interval_context), f"{interval_context}.start"
            )
            end = _integer(_required(interval, "end", interval_context), f"{interval_context}.end")
            if start < horizon_start or end > horizon_end or end <= start:
                raise ProblemValidationError(
                    f"{interval_context} must be a non-empty interval within the planning horizon"
                )
            intervals.append((start, end))
        intervals.sort()
        if any(left[1] > right[0] for left, right in zip(intervals, intervals[1:], strict=False)):
            raise ProblemValidationError(f"{context}.availability intervals must not overlap")
        resources.append(Resource(resource_id, resource_type, capacity, tuple(intervals)))

    tasks: list[Task] = []
    task_ids: set[str] = set()
    for index, raw in enumerate(raw_tasks):
        context = f"tasks[{index}]"
        if not isinstance(raw, dict):
            raise ProblemValidationError(f"{context} must be an object")
        raw_id = raw.get("task_id", raw.get("id"))
        if raw_id is None or not str(raw_id).strip():
            raise ProblemValidationError(f"{context}.task_id is required and must be stable")
        task_id = str(raw_id)
        if task_id in task_ids:
            raise ProblemValidationError(f"duplicate task id {task_id!r}")
        task_ids.add(task_id)
        duration = _integer(_required(raw, "duration", context), f"{context}.duration", minimum=1)
        resource_type = str(_required(raw, "required_resource_type", context))
        if not resource_type.strip():
            raise ProblemValidationError(f"{context}.required_resource_type must not be empty")
        earliest = _integer(_required(raw, "earliest_start", context), f"{context}.earliest_start")
        latest_end = _integer(_required(raw, "latest_end", context), f"{context}.latest_end")
        priority = _integer(_required(raw, "priority", context), f"{context}.priority", minimum=0)
        units = _integer(raw.get("resource_units", 1), f"{context}.resource_units", minimum=1)
        if earliest < horizon_start or latest_end > horizon_end or latest_end - duration < earliest:
            raise ProblemValidationError(f"{context} has an invalid time window or duration")
        if not any(
            resource.resource_type == resource_type and resource.capacity >= units
            for resource in resources
        ):
            raise ProblemValidationError(
                f"{context} requires resource type {resource_type!r}, but no eligible resource has "
                f"capacity {units}"
            )
        tasks.append(Task(task_id, duration, resource_type, earliest, latest_end, priority, units))

    precedence: list[Precedence] = []
    for index, raw in enumerate(data.get("precedence", [])):
        context = f"precedence[{index}]"
        if not isinstance(raw, dict):
            raise ProblemValidationError(f"{context} must be an object")
        before = str(_required(raw, "before_task_id", context))
        after = str(_required(raw, "after_task_id", context))
        if before not in task_ids or after not in task_ids:
            raise ProblemValidationError(f"{context} references an unknown task")
        if before == after:
            raise ProblemValidationError(f"{context} cannot relate a task to itself")
        lag = _integer(raw.get("min_lag", 0), f"{context}.min_lag", minimum=0)
        precedence.append(Precedence(before, after, lag))

    policies = []
    for index, raw in enumerate(data.get("policies", [])):
        context = f"policies[{index}]"
        if not isinstance(raw, dict):
            raise ProblemValidationError(f"{context} must be an object")
        name = raw.get("name", raw.get("type"))
        if not isinstance(name, str) or not name:
            raise ProblemValidationError(f"{context}.name is required")
        if name not in {"max_makespan"}:
            raise ProblemValidationError(f"{context} uses unsupported policy {name!r}")
        parameters = raw.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ProblemValidationError(f"{context}.parameters must be an object")
        policies.append(Policy(name, parameters))

    objectives = _required(data, "objectives", "problem")
    if not isinstance(objectives, dict) or not objectives:
        raise ProblemValidationError("problem.objectives must be a non-empty object")
    unsupported = set(objectives) - {"makespan", "weighted_completion"}
    if unsupported:
        raise ProblemValidationError(f"unsupported objectives: {', '.join(sorted(unsupported))}")
    if any(
        isinstance(weight, bool)
        or not isinstance(weight, (int, float))
        or not isfinite(weight)
        or weight < 0
        for weight in objectives.values()
    ):
        raise ProblemValidationError("objective weights must be finite and non-negative numbers")

    return Problem(
        tuple(tasks),
        tuple(resources),
        tuple(precedence),
        tuple(policies),
        horizon_start,
        horizon_end,
        {str(name): float(weight) for name, weight in objectives.items()},
    )
