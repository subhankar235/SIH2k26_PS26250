"""SQLAlchemy declarative base for backend ORM models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, Uuid, func, text
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql.type_api import TypeEngine
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    """Base class for backend database models."""


class UTCDateTime(TypeDecorator[datetime]):
    """Persist aware timestamps in UTC and restore timezone information on reads."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[datetime]:
        """Use timezone-capable timestamps where supported."""
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """Normalize aware timestamps to UTC before storage."""
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        normalized = value.astimezone(UTC)
        if dialect.name == "sqlite":
            return normalized.replace(tzinfo=None)
        return normalized

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """Return every stored timestamp as an aware UTC datetime."""
        del dialect
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class UUIDPk:
    """Provide a UUID primary key generated in Python."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class CreatedAt:
    """Provide a timezone-aware UTC creation timestamp."""

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )


class Versioned:
    """Provide a monotonically initialized record version."""

    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
