"""Independent schedule checks over plain request and assignment data."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, TypeGuard


def _is_tick(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def check_schedule(
    problem: dict[str, Any], assignments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return schedule violations without importing solver contracts or code."""
    violations: list[dict[str, Any]] = []
    windows = problem.get("windows", {})
    horizon_start = windows.get("horizon_start", windows.get("start"))
    horizon_end = windows.get("horizon_end", windows.get("end"))
    if not _is_tick(horizon_start) or not _is_tick(horizon_end):
        return [
            {
                "rule": "planning_horizon",
                "message": "Planning horizon must contain integer ticks",
                "refs": [],
            }
        ]
    tasks = {str(task.get("task_id", task.get("id"))): task for task in problem.get("tasks", [])}
    resources = {
        str(resource.get("resource_id")): resource for resource in problem.get("resources", [])
    }
    assignments_by_task: dict[str, dict[str, Any]] = {}

    for assignment in assignments:
        task_id = str(assignment.get("task_id"))
        if task_id in assignments_by_task:
            violations.append(
                {
                    "rule": "unique_task_assignment",
                    "message": f"Task {task_id} is assigned more than once",
                    "refs": [task_id],
                }
            )
        assignments_by_task[task_id] = assignment
        task = tasks.get(task_id)
        resource_id = str(assignment.get("resource_id"))
        resource = resources.get(resource_id)
        if task is None:
            violations.append(
                {
                    "rule": "task_reference",
                    "message": f"Assignment references unknown task {task_id}",
                    "refs": [task_id],
                }
            )
            continue
        if resource is None:
            violations.append(
                {
                    "rule": "resource_reference",
                    "message": f"Assignment references unknown resource {resource_id}",
                    "refs": [resource_id],
                }
            )
            continue
        start, end = assignment.get("start"), assignment.get("end")
        earliest_start = task.get("earliest_start", horizon_start)
        latest_end = task.get("latest_end", horizon_end)
        duration = task.get("duration")
        if (
            not _is_tick(start)
            or not _is_tick(end)
            or not _is_tick(earliest_start)
            or not _is_tick(latest_end)
            or not _is_tick(duration)
        ):
            violations.append(
                {
                    "rule": "time_bounds",
                    "message": f"Task {task_id} has invalid or non-integer time bounds",
                    "refs": [task_id],
                }
            )
            continue
        if (
            end <= start
            or end - start != duration
            or start < earliest_start
            or end > latest_end
            or start < horizon_start
            or end > horizon_end
        ):
            violations.append(
                {
                    "rule": "time_bounds",
                    "message": f"Task {task_id} violates its time window",
                    "refs": [task_id],
                }
            )
        if resource.get("resource_type") != task.get("required_resource_type"):
            violations.append(
                {
                    "rule": "resource_eligibility",
                    "message": f"Resource {resource_id} is ineligible for task {task_id}",
                    "refs": [task_id, resource_id],
                }
            )
        available = any(
            isinstance(interval, dict)
            and interval.get("start", end + 1) <= start
            and interval.get("end", start - 1) >= end
            for interval in resource.get("availability", [])
        )
        if not available:
            violations.append(
                {
                    "rule": "resource_availability",
                    "message": f"Resource {resource_id} is unavailable for task {task_id}",
                    "refs": [task_id, resource_id],
                }
            )

    for task_id in tasks.keys() - assignments_by_task.keys():
        violations.append(
            {
                "rule": "task_assigned",
                "message": f"Task {task_id} has no assignment",
                "refs": [task_id],
            }
        )
    for precedence in problem.get("precedence", []):
        before = assignments_by_task.get(precedence.get("before_task_id"))
        after = assignments_by_task.get(precedence.get("after_task_id"))
        if before and after and before["end"] + precedence.get("min_lag", 0) > after["start"]:
            violations.append(
                {
                    "rule": "precedence",
                    "message": "Task precedence is violated",
                    "refs": [precedence["before_task_id"], precedence["after_task_id"]],
                }
            )

    for policy in problem.get("policies", []):
        if policy.get("name", policy.get("type")) == "max_makespan" and assignments:
            maximum = policy.get("parameters", {}).get("maximum")
            if isinstance(maximum, int) and max(item["end"] for item in assignments) > maximum:
                violations.append(
                    {
                        "rule": "planning_policy",
                        "message": "Schedule violates the max_makespan policy",
                        "refs": [],
                    }
                )

    events: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
    for assignment in assignments:
        resource_id = str(assignment.get("resource_id"))
        task = tasks.get(str(assignment.get("task_id")))
        start, end = assignment.get("start"), assignment.get("end")
        if (
            resource_id not in resources
            or task is None
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
        ):
            continue
        units = task.get("resource_units", 1)
        events[resource_id].append((start, 1, units))
        events[resource_id].append((end, -1, units))
    for resource_id, resource_events in events.items():
        active = 0
        capacity = resources[resource_id].get("capacity", 0)
        for _, direction, units in sorted(resource_events, key=lambda event: (event[0], event[1])):
            active += direction * units
            if active > capacity:
                violations.append(
                    {
                        "rule": "resource_capacity",
                        "message": f"Resource {resource_id} capacity is exceeded",
                        "refs": [resource_id],
                    }
                )
                break
    return violations
