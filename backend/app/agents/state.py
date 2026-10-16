"""Typed state and request-scoped service context for agent workflows."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.app.core.enums import AgentRunStatus, VerificationOutcome
from backend.app.schemas.agents import AgentRequestIn, AgentStep, EvidenceRef, ExplanationOut
from backend.app.schemas.validity import ChangeEvent


class EvidenceSummary(BaseModel):
    """Compact, JSON-safe summary of persisted evidence findings."""

    model_config = ConfigDict(extra="forbid")

    issue_ids: list[UUID] = Field(default_factory=list)
    issue_classes: dict[str, int] = Field(default_factory=dict)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    autopsies: list[dict[str, Any]] = Field(default_factory=list)


class ChangeAnalysisOutput(BaseModel):
    """Pydantic response contract for a model-assisted change summary."""

    model_config = ConfigDict(extra="forbid")

    changes: list[ChangeEvent] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    """Typed LangGraph state; persisted independently from ORM run records."""

    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    request: AgentRequestIn
    actor: str = "agent"
    evidence: EvidenceSummary | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    forecast_ids: list[UUID] = Field(default_factory=list)
    changes: list[ChangeEvent] = Field(default_factory=list)
    schedule_id: UUID | None = None
    verification: VerificationOutcome | None = None
    verification_id: UUID | None = None
    retries: int = Field(default=0, ge=0)
    explanation: ExplanationOut | None = None
    status: AgentRunStatus = AgentRunStatus.PENDING
    steps: list[AgentStep] = Field(default_factory=list)
    last_attempt_fingerprint: str | None = None
    error: str | None = None


_ACTIVE_SESSION: ContextVar[Session | None] = ContextVar("agent_active_session", default=None)


@contextmanager
def bind_session(db: Session) -> Iterator[None]:
    """Bind the active caller-owned SQLAlchemy session for one graph invocation."""
    token: Token[Session | None] = _ACTIVE_SESSION.set(db)
    try:
        yield
    finally:
        _ACTIVE_SESSION.reset(token)


def current_session(db: Session | None = None) -> Session:
    """Resolve a node's explicit or invocation-scoped database session."""
    session = db or _ACTIVE_SESSION.get()
    if session is None:
        raise RuntimeError("agent node requires an active database session")
    return session
