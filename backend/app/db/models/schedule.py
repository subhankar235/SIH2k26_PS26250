"""Versioned schedules and solver metadata."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, UUIDPk, Versioned

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


class Schedule(Base, UUIDPk, Versioned):
    """Persist a versioned schedule and its objective and solver metadata."""

    __tablename__ = "schedule"

    parent_schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("schedule.id"), nullable=True
    )
    assignments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_VALUE, default=list, nullable=False
    )
    objectives: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    solver_meta: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    problem_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
