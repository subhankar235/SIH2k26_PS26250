"""Configured source definitions."""

from __future__ import annotations

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, UUIDPk


class Source(Base, UUIDPk):
    """Represent a trusted or observed source of incoming data."""

    __tablename__ = "source"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reliability_prior: Mapped[float] = mapped_column(Float, nullable=False)
