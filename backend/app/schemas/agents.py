"""Agent request, run, and evidence-grounded explanation schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from backend.app.core.enums import AgentRunStatus
from backend.app.schemas.common import APIModel


class AgentRequestIn(APIModel):
    """Request an agent workflow using a structured task payload."""

    request: dict[str, Any]
    seed: int = 0


class AgentStep(APIModel):
    """Describe one agent workflow step."""

    name: str
    status: str
    details: dict[str, Any] = Field(default_factory=dict)


class AgentRunOut(APIModel):
    """Return agent run state and bounded retry information."""

    id: UUID
    status: AgentRunStatus
    steps: list[AgentStep]
    retries: int = Field(ge=0)


class EvidenceRef(APIModel):
    """Identify a versioned evidence object cited by an explanation."""

    kind: str
    id: UUID
    version: int = Field(ge=1)


class ExplanationOut(APIModel):
    """Return an explanation grounded in resolvable evidence references."""

    text: str
    evidence_refs: list[EvidenceRef] = Field(min_length=1)

    @field_validator("evidence_refs")
    @classmethod
    def require_evidence_refs(cls, refs: list[EvidenceRef]) -> list[EvidenceRef]:
        """Reject explanations without evidence citations."""
        if not refs:
            raise ValueError("at least one evidence reference is required")
        return refs
