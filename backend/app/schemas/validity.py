"""Decision validity and incremental reverification schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, Field

from backend.app.core.enums import ValidityStatus, VerificationOutcome
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


class AssumptionIn(APIModel):
    """Register one assumption supporting a new decision."""

    description: str = Field(min_length=1, max_length=1000)
    parameters: dict[str, Any] = Field(default_factory=dict)


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


class VerificationSummary(APIModel):
    """Expose persisted verification metadata without fabricating a result."""

    outcome: VerificationOutcome
    checked_at: AwareDatetime
    violation_count: int = Field(ge=0)
    uncertainty_flags: list[dict[str, Any]] = Field(default_factory=list)


class ValidityEnvelope(APIModel):
    """Describe a decision version and all validity assumptions/dependencies."""

    decision_id: UUID
    decision_type: str
    version: int = Field(ge=1)
    status: ValidityStatus
    assumptions: list[AssumptionOut]
    dependencies: list[DependencyOut]
    verification: VerificationSummary | None = None


class CheckResult(APIModel):
    """Summarize one validity check for a decision."""

    name: str = "check"
    valid: bool | None = None
    required: bool = True
    complete: bool = True
    contradictory: bool = False
    uncertain: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ChangePoint(APIModel):
    """Report a detected change position and its posterior probability."""

    series: str
    index: int = Field(ge=0)
    probability: float = Field(ge=0, le=1)


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


class DecisionState(APIModel):
    """Summarize decision state and whether a fresh verification is applicable."""

    decision_id: UUID
    status: ValidityStatus
    eligible_for_reverification: bool


class ReverifyIn(APIModel):
    """Request incremental reverification after input changes."""

    change_events: list[ChangeEvent] = Field(min_length=1)


class ReverifyOut(APIModel):
    """Return affected decisions and incremental graph work."""

    affected: list[UUID]
    status_changes: list[StatusChange]
    nodes_touched: int = Field(ge=0)
    decision_states: list[DecisionState] = Field(default_factory=list)
    skipped_invalidated: list[UUID] = Field(default_factory=list)
