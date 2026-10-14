"""Decisions, assumptions, and their versioned dependencies."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, CreatedAt, UUIDPk, Versioned

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


class Decision(Base, UUIDPk, CreatedAt, Versioned):
    """Represent a versioned operational decision and its validity state."""

    __tablename__ = "decision"

    decision_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    ref_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)


class Assumption(Base, UUIDPk):
    """Store an assumption attached to a decision."""

    __tablename__ = "assumption"

    decision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("decision.id"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)


class Dependency(Base, UUIDPk):
    """Track an input version that a decision depends on."""

    __tablename__ = "dependency"
    __table_args__ = (Index("ix_dependency_input_id", "input_id"),)

    decision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("decision.id"), nullable=False
    )
    input_type: Mapped[str] = mapped_column(String(64), nullable=False)
    input_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    input_version: Mapped[int] = mapped_column(Integer, nullable=False)
