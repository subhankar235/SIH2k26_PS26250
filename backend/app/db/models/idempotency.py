"""Database record used to persist idempotent API responses."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, UTCDateTime


class IdempotencyRecord(Base):
    """Persist a request fingerprint and the response returned for its key."""

    __tablename__ = "idempotency_record"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_payload: Mapped[object] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
