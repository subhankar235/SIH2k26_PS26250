"""Detect stream changes and materialize versioned input changes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.decision import Dependency
from backend.app.db.models.forecast import Forecast
from backend.app.db.models.record import Record
from backend.app.db.models.schedule import Schedule
from backend.app.schemas.validity import ChangePoint, InputRef
from backend.app.services.ingestion.normaliser import to_utc
from backend.app.services.validity.input_versions import (
    current_input_version,
    input_lineage_ids,
)


def detect_changes(
    series: dict[str, np.ndarray],
    hazard: float = 1 / 250,
    seed: int = 0,
) -> list[ChangePoint]:
    """Apply Bayesian online change-point detection to each named numeric series.

    Args:
        series: Mapping from series key to ordered observations.
        hazard: Per-observation change probability.
        seed: Deterministic seed reserved for optional stochastic model extensions.

    Returns:
        Change points with series key, zero-based position, and posterior probability.

    Raises:
        ValueError: If a series is empty, non-finite, or the hazard is invalid.
    """
    del seed  # Current BOCPD implementation is deterministic.
    from ml.change_point.bocpd import bocpd, change_points
    from ml.change_point.hazard import constant_hazard

    hazard_function = constant_hazard(hazard)
    if not series:
        raise ValueError("series must contain at least one named observation array")
    found: list[ChangePoint] = []
    for key, values in sorted(series.items()):
        observations = np.asarray(values, dtype=float)
        if observations.size < 3:
            raise ValueError(f"series {key!r} must contain at least three observations")
        if not np.isfinite(observations).all():
            raise ValueError(f"series {key!r} must contain only finite observations")
        posterior = bocpd(observations, hazard_function)
        for index in change_points(posterior, threshold=0.5):
            previous_mode = int(np.argmax(posterior[index, : index + 1]))
            found.append(
                ChangePoint(
                    series=key,
                    index=index,
                    probability=float(posterior[index + 1, :previous_mode].sum()),
                )
            )
    return found


def changed_inputs_since(db: Session, since: datetime) -> list[InputRef]:
    """Return logical input references whose persisted versions changed since a timestamp.

    Args:
        db: Active synchronous database session.
        since: Aware lower bound for record ingestion time.

    Returns:
        Sorted references to old dependency ids with the latest persisted logical version.

    Raises:
        ValueError: If the time boundary is naive.
        SQLAlchemyError: If input change rows cannot be queried.
    """
    if since.tzinfo is None or since.utcoffset() is None:
        raise ValueError("since must be timezone-aware")
    lower_bound = to_utc(since)
    refs: dict[tuple[str, UUID], InputRef] = {}
    changed_records = db.scalars(
        select(Record)
        .where(Record.ingest_time > lower_bound)
        .order_by(Record.ingest_time, Record.id)
    ).all()
    for record in changed_records:
        lineage_ids = input_lineage_ids(db, "record", record.id) or {record.id}
        current_version = current_input_version(db, "record", record.id) or record.version
        for input_id in lineage_ids:
            input_types = set(
                db.scalars(
                    select(Dependency.input_type).where(Dependency.input_id == input_id).distinct()
                ).all()
            ) or {"record"}
            for input_type in input_types:
                key = (input_type, input_id)
                previous = refs.get(key)
                if previous is None or current_version > previous.input_version:
                    refs[key] = InputRef(
                        input_type=input_type,
                        input_id=input_id,
                        input_version=current_version,
                    )

    changed_forecasts = db.scalars(
        select(Forecast)
        .where(Forecast.created_at > lower_bound)
        .order_by(Forecast.created_at, Forecast.id)
    ).all()
    for forecast in changed_forecasts:
        version = current_input_version(db, "forecast", forecast.id) or forecast.version
        for input_id in input_lineage_ids(db, "forecast", forecast.id) or {forecast.id}:
            refs[("forecast", input_id)] = InputRef(
                input_type="forecast", input_id=input_id, input_version=version
            )

    changed_schedules = db.scalars(
        select(Schedule)
        .where(Schedule.created_at > lower_bound)
        .order_by(Schedule.created_at, Schedule.id)
    ).all()
    for schedule in changed_schedules:
        version = current_input_version(db, "schedule", schedule.id) or schedule.version
        for input_id in input_lineage_ids(db, "schedule", schedule.id) or {schedule.id}:
            refs[("schedule", input_id)] = InputRef(
                input_type="schedule", input_id=input_id, input_version=version
            )
    return sorted(refs.values(), key=lambda ref: (ref.input_type, str(ref.input_id)))
