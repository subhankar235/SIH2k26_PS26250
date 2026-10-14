"""Evidence claims, issue, provenance, and autopsy schemas."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from backend.app.core.enums import IssueClass
from backend.app.schemas.common import APIModel


class ClaimOut(APIModel):
    """Return an attributed evidence claim."""

    id: UUID
    record_id: UUID
    attribute: str
    value: Any
    source_id: UUID
    observed_at: AwareDatetime
    superseded_by: UUID | None = None


class IssueOut(APIModel):
    """Return a detected evidence-quality issue."""

    id: UUID
    issue_class: IssueClass
    claim_ids: list[UUID]
    detected_at: AwareDatetime
    status: Literal["open", "resolved"]
    details: dict[str, Any]


class ProvenanceStep(APIModel):
    """Describe one step in a record's provenance history."""

    record_id: UUID
    action: str
    timestamp: AwareDatetime
    version: int | None = None
    source_id: UUID | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AutopsyOut(APIModel):
    """Explain an evidence issue with provenance and uncertainty."""

    issue: IssueOut
    claims: list[ClaimOut]
    provenance: list[ProvenanceStep]
    missing_information: list[str]
    uncertainty: dict[str, Any]
