"""Assignment-level diffs and schedule stability metrics."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.core.exceptions import NotFoundError
from backend.app.db.models.schedule import Schedule
from backend.app.schemas.replanning import MovedAssignment, ScheduleDiff


def _assignments(schedule: Schedule) -> dict[str, dict[str, object]]:
    """Index a schedule's assignments by task id and reject malformed duplicates."""
    indexed: dict[str, dict[str, object]] = {}
    for item in schedule.assignments:
        task_id = item.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError(f"schedule {schedule.id} contains an assignment without a task id")
        if task_id in indexed:
            raise ValueError(
                f"schedule {schedule.id} contains duplicate task assignment {task_id!r}"
            )
        indexed[task_id] = item
    return indexed


def _location(item: dict[str, object]) -> tuple[object, object, object]:
    """Return the fields that define assignment identity across schedule versions."""
    return item.get("resource_id"), item.get("start"), item.get("end")


def diff(old: Schedule, new: Schedule) -> ScheduleDiff:
    """Classify assignments as added, removed, moved, or unchanged.

    An assignment is moved when its resource or either time boundary changes.
    Additional payload metadata does not count as movement.

    Args:
        old: Previous schedule version.
        new: Candidate or persisted replacement schedule.

    Returns:
        Assignment-level schedule diff.

    Raises:
        ValueError: If either schedule contains malformed or duplicate task assignments.
    """
    old_by_task = _assignments(old)
    new_by_task = _assignments(new)
    old_ids, new_ids = set(old_by_task), set(new_by_task)
    added = [new_by_task[task_id] for task_id in sorted(new_ids - old_ids)]
    removed = [old_by_task[task_id] for task_id in sorted(old_ids - new_ids)]
    moved: list[MovedAssignment] = []
    unchanged = 0
    for task_id in sorted(old_ids & new_ids):
        before, after = old_by_task[task_id], new_by_task[task_id]
        if _location(before) == _location(after):
            unchanged += 1
        else:
            moved.append(
                MovedAssignment(
                    task_id=task_id,
                    before=before,
                    after=after,
                )
            )
    return ScheduleDiff(added=added, removed=removed, moved=moved, unchanged=unchanged)


def stability(schedule_diff: ScheduleDiff) -> float:
    """Return the fraction of old assignments that remain unchanged.

    Added tasks do not reduce stability because they were not in the old plan.
    An old schedule with no assignments is fully stable by convention.

    Args:
        schedule_diff: Previously computed assignment diff.

    Returns:
        A value in ``[0, 1]``.
    """
    total = schedule_diff.unchanged + len(schedule_diff.removed) + len(schedule_diff.moved)
    return schedule_diff.unchanged / total if total else 1.0


def diff_by_id(db: Session, old_id: UUID, new_id: UUID) -> ScheduleDiff:
    """Load two persisted schedules and return their assignment diff.

    Args:
        db: Active synchronous database session.
        old_id: Earlier schedule UUID.
        new_id: Later schedule UUID.

    Returns:
        The assignment-level diff.

    Raises:
        NotFoundError: If either schedule does not exist.
        ValueError: If either schedule contains malformed assignments.
    """
    old = db.get(Schedule, old_id)
    if old is None:
        raise NotFoundError("Schedule not found", {"id": str(old_id)})
    new = db.get(Schedule, new_id)
    if new is None:
        raise NotFoundError("Schedule not found", {"id": str(new_id)})
    return diff(old, new)
