"""Synthetic simulation and benchmark experiment runs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, CreatedAt, UUIDPk

JSON_VALUE = JSON().with_variant(JSONB(), "postgresql")


class ExperimentRun(Base, UUIDPk, CreatedAt):
    """Store a seeded experiment configuration and its result metrics."""

    __tablename__ = "experiment_run"

    scenario: Mapped[str] = mapped_column(String(255), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, default=dict, nullable=False)
    mlflow_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
