"""Assignment diff and schedule-stability contract tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from backend.app.db.models import Schedule
from backend.app.services.replanning.schedule_diff import diff, stability


def _schedule(assignments: list[dict[str, object]]) -> Schedule:
    """Build a transient schedule row for pure diff tests."""
    return Schedule(
        id=uuid4(),
        version=1,
        created_at=datetime.now(UTC),
        assignments=assignments,
        objectives={},
        solver_meta={},
        status="verified",
        problem_hash="b" * 64,
    )


def test_schedule_diff_added_removed_moved_and_unchanged() -> None:
    """Classify task changes and calculate the fraction of prior work unchanged."""
    old = _schedule(
        [
            {"task_id": "same", "resource_id": "crew-a", "start": 0, "end": 1},
            {"task_id": "move", "resource_id": "crew-a", "start": 1, "end": 2},
            {"task_id": "remove", "resource_id": "crew-b", "start": 0, "end": 2},
        ]
    )
    new = _schedule(
        [
            {"task_id": "same", "resource_id": "crew-a", "start": 0, "end": 1},
            {"task_id": "move", "resource_id": "crew-b", "start": 2, "end": 3},
            {"task_id": "add", "resource_id": "crew-a", "start": 1, "end": 2},
        ]
    )

    result = diff(old, new)

    assert [item["task_id"] for item in result.added] == ["add"]
    assert [item["task_id"] for item in result.removed] == ["remove"]
    assert [item.task_id for item in result.moved] == ["move"]
    assert result.unchanged == 1
    assert stability(result) == 1 / 3
