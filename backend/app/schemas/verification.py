"""Independent schedule and decision verification schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from backend.app.core.enums import VerificationOutcome
from backend.app.schemas.common import APIModel


class VerifyIn(APIModel):
    """Request verification for a persisted target."""

    target_type: str
    target_id: UUID


class Violation(APIModel):
    """Describe a violated verification rule and its evidence references."""

    rule: str
    message: str
    refs: list[str]


class UncertaintyFlag(APIModel):
    """Describe an unresolved source of decision uncertainty."""

    code: str
    message: str
    refs: list[str] = Field(default_factory=list)


class VerificationOut(APIModel):
    """Return authoritative verification results and uncertainty flags."""

    outcome: VerificationOutcome
    violations: list[Violation]
    uncertainty_flags: list[UncertaintyFlag]
