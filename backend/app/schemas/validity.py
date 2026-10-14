"""Decision validity and incremental reverification schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, Field

from backend.app.core.enums import ValidityStatus
from backend.app.schemas.common import APIModel


class InputRef(APIModel):
    """Identify a versioned input that may affect a decision."""

    input_type: str
    input_id: UUID
    input_version: int = Field(ge=1)


class AssumptionOut(APIModel):
    """Return a recorded decision assumption."""

    id: UUID
    description: str
    parameters: dict[str, Any]


class DependencyOut(APIModel):
    """Return a versioned input dependency for a decision."""

    input_type: str
    input_id: UUID
    input_version: int = Field(ge=1)


class DecisionOut(APIModel):
    """Return a decision and the inputs that support its validity."""

    id: UUID
    type: str = Field(validation_alias="decision_type")
    version: int = Field(ge=1)
    status: ValidityStatus
    assumptions: list[AssumptionOut]
    dependencies: list[DependencyOut]


class ChangeEvent(APIModel):
    """Describe a changed input and its old and new versions."""

    input_type: str
    input_id: UUID
    old_version: int | None = Field(default=None, ge=1)
    new_version: int = Field(ge=1)
    changed_at: AwareDatetime | None = None


class StatusChange(APIModel):
    """Report a decision validity transition."""

    decision_id: UUID
    old_status: ValidityStatus
    new_status: ValidityStatus


class ReverifyIn(APIModel):
    """Request incremental reverification after input changes."""

    change_events: list[ChangeEvent] = Field(min_length=1)


class ReverifyOut(APIModel):
    """Return affected decisions and incremental graph work."""

    affected: list[UUID]
    status_changes: list[StatusChange]
    nodes_touched: int = Field(ge=0)
