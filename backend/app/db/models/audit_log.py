"""Append-only audit entries for backend state changes."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, CreatedAt, UUIDPk

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


class AuditEntry(Base, UUIDPk, CreatedAt):
    """Store a small, append-only audit reference for a state change."""

    __tablename__ = "audit_entry"
    __table_args__ = (Index("ix_audit_entry_entity", "entity_type", "entity_id"),)

    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    before_ref: Mapped[dict[str, Any] | None] = mapped_column(JSON_VALUE, nullable=True)
    after_ref: Mapped[dict[str, Any] | None] = mapped_column(JSON_VALUE, nullable=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(255), nullable=False)
