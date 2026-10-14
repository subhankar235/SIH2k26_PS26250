"""Compare persisted schedule assignments without solver dependencies."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.core.exceptions import NotFoundError, RequestValidationFailed
from backend.app.db.models.schedule import Schedule
from backend.app.schemas.replanning import MovedAssignment, ScheduleDiff


def diff_schedules(
    old_assignments: list[dict[str, Any]], new_assignments: list[dict[str, Any]]
) -> ScheduleDiff:
    """Classify task assignments as added, removed, moved, or unchanged."""
    old_by_task = _by_task(old_assignments, "old")
    new_by_task = _by_task(new_assignments, "new")
    old_ids, new_ids = old_by_task.keys(), new_by_task.keys()
    added = [new_by_task[task_id] for task_id in sorted(new_ids - old_ids)]
    removed = [old_by_task[task_id] for task_id in sorted(old_ids - new_ids)]
    moved = []
    unchanged = 0
    for task_id in sorted(old_ids & new_ids):
        before, after = old_by_task[task_id], new_by_task[task_id]
        if before == after:
            unchanged += 1
        else:
            moved.append(MovedAssignment(task_id=task_id, before=before, after=after))
    return ScheduleDiff(added=added, removed=removed, moved=moved, unchanged=unchanged)


def diff_by_id(db: Session, old_id: UUID, new_id: UUID) -> ScheduleDiff:
    """Load and compare two persisted schedule versions."""
    old = db.get(Schedule, old_id)
    new = db.get(Schedule, new_id)
    if old is None:
        raise NotFoundError("Schedule not found", {"schedule_id": str(old_id)})
    if new is None:
        raise NotFoundError("Schedule not found", {"schedule_id": str(new_id)})
    return diff_schedules(old.assignments, new.assignments)


def _by_task(assignments: list[dict[str, Any]], version: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for assignment in assignments:
        task_id = assignment.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise RequestValidationFailed(f"{version} schedule contains an invalid task id")
        if task_id in indexed:
            raise RequestValidationFailed(
                f"{version} schedule contains multiple assignments for task {task_id}"
            )
        indexed[task_id] = assignment
    return indexed
