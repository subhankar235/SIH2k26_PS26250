"""Independent plain-Python schedule feasibility checks."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from backend.app.schemas.verification import Violation


@dataclass(frozen=True)
class ScheduleData:
    """Plain assignment values consumed by the independent verifier."""

    assignments: list[dict[str, Any]]


@dataclass(frozen=True)
class ProblemData:
    """Plain problem values required by the independent verifier."""

    tasks: list[dict[str, Any]]
    resources: list[dict[str, Any]]
    precedence: list[dict[str, Any]] = field(default_factory=list)
    policies: list[dict[str, Any]] = field(default_factory=list)
    horizon: int = 0


def _violation(rule: str, message: str, *refs: object) -> Violation:
    """Build a verification violation with stable string references."""
    return Violation(rule=rule, message=message, refs=[str(ref) for ref in refs])


def check_capacity(schedule: ScheduleData, problem: ProblemData) -> list[Violation]:
    """Check task assignment uniqueness, resource compatibility, and capacity.

    Args:
        schedule: Candidate assignment values.
        problem: Plain task and resource definitions.

    Returns:
        Violations for duplicate/missing assignments, unknown resources, or capacity.
    """
    violations: list[Violation] = []
    tasks = {str(task.get("id")): task for task in problem.tasks}
    resources = {str(resource.get("id")): resource for resource in problem.resources}
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for assignment in schedule.assignments:
        by_task[str(assignment.get("task_id", ""))].append(assignment)

    for task_id in tasks:
        assignments = by_task.get(task_id, [])
        if len(assignments) != 1:
            violations.append(
                _violation("assignment_count", "Task must have exactly one assignment", task_id)
            )
    for task_id in by_task.keys() - tasks.keys():
        violations.append(_violation("unknown_task", "Assignment refers to unknown task", task_id))

    for task_id, assignments in by_task.items():
        for assignment in assignments:
            resource_id = str(assignment.get("resource_id", ""))
            resource = resources.get(resource_id)
            task = tasks.get(task_id)
            if resource is None:
                violations.append(
                    _violation(
                        "unknown_resource",
                        "Assignment refers to unknown resource",
                        task_id,
                        resource_id,
                    )
                )
            elif task is not None:
                required_type = str(task.get("resource_type", "any"))
                actual_type = str(resource.get("type", resource.get("resource_type", "")))
                if required_type not in {"*", "any", actual_type}:
                    violations.append(
                        _violation(
                            "resource_type",
                            "Resource type does not match task",
                            task_id,
                            resource_id,
                        )
                    )

    for resource_id, resource in resources.items():
        try:
            capacity = int(resource.get("capacity", 1))
        except (TypeError, ValueError):
            violations.append(
                _violation("resource_capacity", "Resource capacity is malformed", resource_id)
            )
            continue
        if capacity < 1:
            violations.append(
                _violation("resource_capacity", "Resource capacity must be positive", resource_id)
            )
            continue
        timeline: list[tuple[int, int, str]] = []
        for assignment in schedule.assignments:
            if str(assignment.get("resource_id", "")) != resource_id:
                continue
            try:
                start = int(assignment["start"])
                end = int(assignment["end"])
                task_id = str(assignment["task_id"])
            except (KeyError, TypeError, ValueError):
                violations.append(
                    _violation(
                        "assignment_shape",
                        "Assignment has invalid time values",
                        resource_id,
                    )
                )
                continue
            if end <= start:
                violations.append(
                    _violation("assignment_interval", "Assignment end must follow start", task_id)
                )
                continue
            timeline.extend(((start, 1, task_id), (end, -1, task_id)))
        occupancy = 0
        for _, delta, task_id in sorted(timeline, key=lambda point: (point[0], point[1])):
            occupancy += delta
            if occupancy > capacity:
                violations.append(
                    _violation("capacity", "Resource capacity is exceeded", resource_id, task_id)
                )
                break
    return violations


def check_time_windows(schedule: ScheduleData, problem: ProblemData) -> list[Violation]:
    """Check task start windows, problem horizon, and resource availability.

    Args:
        schedule: Candidate assignment values.
        problem: Plain task/resource windows and horizon.

    Returns:
        Time-window and availability violations.
    """
    violations: list[Violation] = []
    tasks = {str(task.get("id")): task for task in problem.tasks}
    resources = {str(resource.get("id")): resource for resource in problem.resources}
    for assignment in schedule.assignments:
        task_id = str(assignment.get("task_id", ""))
        resource_id = str(assignment.get("resource_id", ""))
        task = tasks.get(task_id)
        resource = resources.get(resource_id)
        try:
            start_raw, end_raw = assignment["start"], assignment["end"]
            if (
                not isinstance(start_raw, int)
                or isinstance(start_raw, bool)
                or not isinstance(end_raw, int)
                or isinstance(end_raw, bool)
            ):
                raise ValueError("assignment times must be integers")
            start, end = start_raw, end_raw
        except (KeyError, TypeError, ValueError):
            violations.append(
                _violation("assignment_shape", "Assignment has invalid time values", task_id)
            )
            continue
        if start < 0 or end <= start:
            violations.append(
                _violation("assignment_interval", "Assignment interval is invalid", task_id)
            )
            continue
        if task is not None:
            try:
                expected_duration = int(task["duration"])
            except (KeyError, TypeError, ValueError):
                violations.append(
                    _violation("task_duration", "Task duration is malformed", task_id)
                )
            else:
                if end - start != expected_duration:
                    violations.append(
                        _violation(
                            "task_duration",
                            "Assignment duration does not match task duration",
                            task_id,
                        )
                    )
        if task is not None:
            try:
                earliest = int(task.get("earliest", 0))
                latest = int(task.get("latest", problem.horizon))
            except (TypeError, ValueError):
                violations.append(
                    _violation("time_window_shape", "Task time window is malformed", task_id)
                )
            else:
                if start < earliest or start > latest:
                    violations.append(
                        _violation(
                            "time_window",
                            "Task starts outside its permitted window",
                            task_id,
                        )
                    )
        if problem.horizon > 0 and end > problem.horizon:
            violations.append(
                _violation("horizon", "Task ends after the planning horizon", task_id)
            )
        if resource is not None:
            available = resource.get("available", [[0, problem.horizon]])
            try:
                within_availability = any(
                    int(left) <= start and end <= int(right) for left, right in available
                )
            except (TypeError, ValueError):
                within_availability = False
            if not within_availability:
                violations.append(
                    _violation(
                        "availability",
                        "Assignment is outside resource availability",
                        task_id,
                        resource_id,
                    )
                )
    return violations


def check_precedence(schedule: ScheduleData, problem: ProblemData) -> list[Violation]:
    """Check directed precedence edges and their minimum gaps.

    Args:
        schedule: Candidate assignment values.
        problem: Plain precedence constraints.

    Returns:
        Violations where an after-task starts too early.
    """
    assignments = {str(item.get("task_id", "")): item for item in schedule.assignments}
    violations: list[Violation] = []
    for precedence in problem.precedence:
        before, after = str(precedence.get("before", "")), str(precedence.get("after", ""))
        if before not in assignments or after not in assignments:
            continue
        try:
            minimum = int(precedence.get("min_gap", 0))
            after_start = int(assignments[after]["start"])
            before_end = int(assignments[before]["end"])
        except (TypeError, ValueError, KeyError):
            violations.append(
                _violation("precedence_shape", "Precedence values are malformed", before, after)
            )
            continue
        if after_start < before_end + minimum:
            violations.append(
                _violation(
                    "precedence",
                    "Task precedence or minimum gap is violated",
                    before,
                    after,
                )
            )
    return violations


def check_policies(schedule: ScheduleData, problem: ProblemData) -> list[Violation]:
    """Check supported forbidden-pair, no-overlap, and total-hours policies.

    Args:
        schedule: Candidate assignment values.
        problem: Plain policy definitions.

    Returns:
        Violations for each policy that the candidate schedule breaks.
    """
    violations: list[Violation] = []
    assignments = {str(item.get("task_id", "")): item for item in schedule.assignments}
    for policy in problem.policies:
        if not isinstance(policy, dict):
            violations.append(_violation("policy_shape", "Policy entry must be an object"))
            continue
        name = policy.get("name")
        params = policy.get("params", {})
        if not isinstance(params, dict):
            violations.append(
                _violation("policy_shape", "Policy parameters must be an object", name)
            )
            continue
        if name == "forbidden_pairs":
            pairs = params.get("pairs", [])
            if not isinstance(pairs, list):
                violations.append(
                    _violation("policy_shape", "forbidden_pairs requires a pair list")
                )
                continue
            for pair in pairs:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    violations.append(
                        _violation("policy_shape", "forbidden_pairs entry is malformed")
                    )
                    continue
                left_id, right_id = str(pair[0]), str(pair[1])
                left, right = assignments.get(left_id), assignments.get(right_id)
                if (
                    left is not None
                    and right is not None
                    and left["resource_id"] == right["resource_id"]
                ):
                    try:
                        overlaps = int(left["start"]) < int(right["end"]) and int(
                            right["start"]
                        ) < int(left["end"])
                    except (TypeError, ValueError, KeyError):
                        violations.append(
                            _violation("policy_shape", "Forbidden pair assignment is malformed")
                        )
                        continue
                    if overlaps:
                        violations.append(
                            _violation(
                                "forbidden_pair",
                                "Forbidden tasks overlap on one resource",
                                left_id,
                                right_id,
                            )
                        )
        elif name == "no_overlap":
            ids = params.get("task_ids", [])
            if not isinstance(ids, list):
                violations.append(
                    _violation("policy_shape", "no_overlap requires a task id list")
                )
                continue
            assigned = [assignments[str(task_id)] for task_id in ids if str(task_id) in assignments]
            for index, left in enumerate(assigned):
                for right in assigned[index + 1 :]:
                    if left.get("resource_id") != right.get("resource_id"):
                        continue
                    try:
                        overlaps = int(left["start"]) < int(right["end"]) and int(
                            right["start"]
                        ) < int(left["end"])
                    except (TypeError, ValueError, KeyError):
                        violations.append(
                            _violation("policy_shape", "no_overlap assignment is malformed")
                        )
                        continue
                    if overlaps:
                        violations.append(
                            _violation(
                                "no_overlap",
                                "Tasks governed by no_overlap policy overlap",
                                left["task_id"],
                                right["task_id"],
                            )
                        )
        elif name == "max_total_hours":
            try:
                maximum = int(params.get("hours", 0))
            except (TypeError, ValueError):
                violations.append(
                    _violation("policy_shape", "max_total_hours requires integer hours")
                )
                continue
            if maximum < 0:
                violations.append(
                    _violation("policy_shape", "max_total_hours must not be negative")
                )
                continue
            per_resource: dict[str, int] = defaultdict(int)
            for assignment in schedule.assignments:
                try:
                    duration = int(assignment["end"]) - int(assignment["start"])
                    resource_id = str(assignment["resource_id"])
                except (TypeError, ValueError, KeyError):
                    continue
                per_resource[resource_id] += duration
            for resource_id, hours in per_resource.items():
                if hours > maximum:
                    violations.append(
                        _violation(
                            "max_total_hours",
                            "Resource exceeds max_total_hours",
                            resource_id,
                        )
                    )
        elif name == "fixed_assignments":
            expected = params.get("assignments", [])
            if not isinstance(expected, list):
                violations.append(
                    _violation("policy_shape", "fixed_assignments requires an assignment list")
                )
                continue
            for fixed in expected:
                if not isinstance(fixed, dict):
                    violations.append(
                        _violation("policy_shape", "Fixed assignment entry is malformed")
                    )
                    continue
                task_id = str(fixed.get("task_id", ""))
                actual = assignments.get(task_id)
                if actual is None or any(
                    actual.get(key) != fixed.get(key)
                    for key in ("resource_id", "start", "end")
                ):
                    violations.append(
                        _violation(
                            "fixed_assignment",
                            "Schedule does not preserve a fixed assignment",
                            task_id,
                        )
                    )
        else:
            violations.append(
                _violation("unsupported_policy", "Policy cannot be independently verified", name)
            )
    return violations


def check_all(schedule: ScheduleData, problem: ProblemData) -> list[Violation]:
    """Run every independent feasibility rule and collect all violations.

    Args:
        schedule: Candidate schedule values.
        problem: Plain scheduling problem values.

    Returns:
        All capacity, time-window, precedence, and policy violations.
    """
    return [
        *check_capacity(schedule, problem),
        *check_time_windows(schedule, problem),
        *check_precedence(schedule, problem),
        *check_policies(schedule, problem),
    ]
