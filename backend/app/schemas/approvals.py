"""Human approval queue and decision schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, Field

from backend.app.core.enums import ApprovalDecision, VerificationOutcome
from backend.app.schemas.common import APIModel


class ApprovalQueueItem(APIModel):
    """Represent a verified or uncertain target awaiting human review."""

    id: UUID
    target_type: str
    target_id: UUID
    outcome: VerificationOutcome
    queued_at: AwareDatetime
    summary: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecisionIn(APIModel):
    """Submit a human approval decision with rationale."""

    decision: ApprovalDecision
    rationale: str = Field(min_length=10, max_length=4000)


class ApprovalOut(APIModel):
    """Return the persisted approval decision."""

    id: UUID
    target_type: str
    target_id: UUID
    approver: str
    decision: ApprovalDecision
    rationale: str
    decided_at: AwareDatetime
