"""Evidence claims, quality issues, and graph edges."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, UUIDPk

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


class Claim(Base, UUIDPk):
    """Store an attributed assertion about a record."""

    __tablename__ = "claim"
    __table_args__ = (Index("ix_claim_record", "record_id"),)

    record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("record.id"), nullable=False
    )
    attribute: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[Any] = mapped_column(JSON_VALUE, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source.id"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("claim.id"), nullable=True
    )


class Issue(Base, UUIDPk):
    """Store a detected evidence-quality issue and its supporting claims."""

    __tablename__ = "issue"

    issue_class: Mapped[str] = mapped_column(String(32), nullable=False)
    claim_ids: Mapped[list[str]] = mapped_column(JSON_VALUE, default=list, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)


class EvidenceEdge(Base, UUIDPk):
    """Represent a timestamped relation between evidence graph nodes."""

    __tablename__ = "evidence_edge"

    from_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    to_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    relation: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
