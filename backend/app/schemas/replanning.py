"""Schedule replanning request, diff, and response schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from backend.app.schemas.common import APIModel
from backend.app.schemas.planning import ScheduleOut
from backend.app.schemas.validity import ChangeEvent


class ReplanIn(APIModel):
    """Request a replan for a schedule after input changes."""

    schedule_id: UUID
    changes: list[ChangeEvent] = Field(min_length=1)


class MovedAssignment(APIModel):
    """Describe an assignment moved between schedule versions."""

    task_id: str
    before: dict[str, Any]
    after: dict[str, Any]


class ScheduleDiff(APIModel):
    """Summarize added, removed, moved, and unchanged work."""

    added: list[dict[str, Any]]
    removed: list[dict[str, Any]]
    moved: list[MovedAssignment]
    unchanged: int = Field(ge=0)


class ReplanOut(APIModel):
    """Return a newly verified schedule and the change summary."""

    schedule: ScheduleOut
    diff: ScheduleDiff
    fallback_to_full_solve: bool
