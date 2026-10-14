"""Agent workflow runs and persisted graph state."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, CreatedAt, UUIDPk

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


class AgentRun(Base, UUIDPk, CreatedAt):
    """Persist agent requests, checkpoints, status, and explanation output."""

    __tablename__ = "agent_run"
    __table_args__ = (Index("ix_agent_run_idempotency_key", "idempotency_key", unique=True),)

    request: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    graph_state: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    checkpoints: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_VALUE, default=list, nullable=False
    )
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
