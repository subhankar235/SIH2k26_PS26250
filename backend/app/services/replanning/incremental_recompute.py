"""Guarded replanning entry point for the current ChangeEvent request contract."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.core.exceptions import NotFoundError, RequestValidationFailed
from backend.app.db.models.schedule import Schedule
from backend.app.schemas.validity import ChangeEvent


def replan(
    db: Session,
    schedule_id: UUID,
    changes: Sequence[ChangeEvent],
    actor: str,
) -> None:
    """Reject replanning until changed input values can be mapped safely.

    ChangeEvent provides identifiers and versions only; it does not carry the
    updated planning snapshot or task/resource mappings required by the solver.
    """
    _ = actor
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise NotFoundError("Schedule not found", {"schedule_id": str(schedule_id)})
    raise RequestValidationFailed(
        "Replanning cannot build a consistent updated optimization problem: "
        "ChangeEvent supplies input IDs and versions but no updated task/resource values, "
        "and this schedule has no input-version dependencies",
        {
            "schedule_id": str(schedule_id),
            "change_count": len(changes),
            "stored_input_versions": schedule.solver_meta.get("input_versions", {}),
        },
    )
