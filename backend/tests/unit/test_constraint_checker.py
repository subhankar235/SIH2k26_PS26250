"""Independent checker coverage for each declared scheduling constraint class."""

from __future__ import annotations

from backend.app.services.verification.constraint_checker import (
    ProblemData,
    ScheduleData,
    check_all,
)


def test_constraint_checker_reports_assignment_capacity_window_and_precedence_violations() -> None:
    """Detect missing/unknown assignments, resource capacity, timing, and precedence."""
    problem = ProblemData(
        tasks=[
            {"id": "before", "duration": 2, "resource_type": "crew", "earliest": 2, "latest": 3},
            {"id": "after", "duration": 1, "resource_type": "crew", "earliest": 0, "latest": 4},
            {"id": "missing", "duration": 1, "resource_type": "crew", "earliest": 0, "latest": 4},
        ],
        resources=[
            {"id": "crew", "type": "crew", "capacity": 1, "available": [[2, 5]]}
        ],
        precedence=[{"before": "before", "after": "after", "min_gap": 1}],
        horizon=5,
    )
    schedule = ScheduleData(
        assignments=[
            {"task_id": "before", "resource_id": "crew", "start": 0, "end": 2},
            {"task_id": "after", "resource_id": "crew", "start": 1, "end": 2},
            {"task_id": "unknown", "resource_id": "missing-resource", "start": 1, "end": 2},
        ]
    )

    rules = {item.rule for item in check_all(schedule, problem)}

    assert {
        "assignment_count",
        "unknown_task",
        "unknown_resource",
        "time_window",
        "availability",
        "capacity",
        "precedence",
    } <= rules


def test_constraint_checker_reports_each_policy_violation() -> None:
    """Independently check forbidden pairs, no-overlap, max hours, and fixed work."""
    problem = ProblemData(
        tasks=[
            {"id": "a", "duration": 2, "resource_type": "crew", "earliest": 0, "latest": 4},
            {"id": "b", "duration": 2, "resource_type": "crew", "earliest": 0, "latest": 4},
        ],
        resources=[{"id": "crew", "type": "crew", "capacity": 2, "available": [[0, 5]]}],
        policies=[
            {"name": "forbidden_pairs", "params": {"pairs": [["a", "b"]]}},
            {"name": "no_overlap", "params": {"task_ids": ["a", "b"]}},
            {"name": "max_total_hours", "params": {"hours": 2}},
            {
                "name": "fixed_assignments",
                "params": {
                    "assignments": [
                        {"task_id": "a", "resource_id": "crew", "start": 4, "end": 5}
                    ]
                },
            },
        ],
        horizon=5,
    )
    schedule = ScheduleData(
        assignments=[
            {"task_id": "a", "resource_id": "crew", "start": 0, "end": 2},
            {"task_id": "b", "resource_id": "crew", "start": 1, "end": 3},
        ]
    )

    rules = {item.rule for item in check_all(schedule, problem)}

    assert {"forbidden_pair", "no_overlap", "max_total_hours", "fixed_assignment"} <= rules
