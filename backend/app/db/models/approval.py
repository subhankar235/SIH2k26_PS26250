"""Independent verification results and human approval decisions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, UTCDateTime, UUIDPk

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


class VerificationResult(Base, UUIDPk):
    """Persist an independent verification outcome and its findings."""

    __tablename__ = "verification_result"

    target_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    violations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_VALUE, default=list, nullable=False
    )
    uncertainty_flags: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_VALUE, default=list, nullable=False
    )
    checked_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(UTC), nullable=False
    )


class Approval(Base, UUIDPk):
    """Persist an auditable human decision for a verified target."""

    __tablename__ = "approval"

    target_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    approver: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(String(4000), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(UTC), nullable=False
    )
