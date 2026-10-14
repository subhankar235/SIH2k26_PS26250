"""Raw ingested events and normalized versioned records."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, UTCDateTime, UUIDPk, Versioned

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


class RawEvent(Base, UUIDPk):
    """Persist the original event payload and its source timestamps."""

    __tablename__ = "raw_event"
    __table_args__ = (
        UniqueConstraint("source_id", "source_event_id", name="uq_raw_event_source_event"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source.id"), nullable=False, index=True
    )
    source_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    event_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    ingest_time: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(UTC), nullable=False
    )


class Record(Base, UUIDPk, Versioned):
    """Persist a normalized, versioned record without deleting prior versions."""

    __tablename__ = "record"
    __table_args__ = (Index("ix_record_entity_source", "entity_id", "source_type"),)

    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    normalised_payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source.id"), nullable=False
    )
    raw_event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("raw_event.id"), nullable=False
    )
    event_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    ingest_time: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(UTC), nullable=False
    )
    flags: Mapped[list[str]] = mapped_column(JSON_VALUE, default=list, nullable=False)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("record.id"), nullable=True
    )
