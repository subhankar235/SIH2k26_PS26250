"""Versioned model forecasts and their calibration metadata."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, CreatedAt, UUIDPk, Versioned

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


class Forecast(Base, UUIDPk, Versioned, CreatedAt):
    """Store forecast points, uncertainty, and the versions of its inputs."""

    __tablename__ = "forecast"

    target: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[list[dict[str, Any]]] = mapped_column(JSON_VALUE, nullable=False)
    calibration_meta: Mapped[dict[str, Any]] = mapped_column(
        JSON_VALUE, default=dict, nullable=False
    )
    input_versions: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    high_uncertainty: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
