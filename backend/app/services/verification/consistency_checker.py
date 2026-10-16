"""Check persisted schedule provenance, forecast links, and evidence links."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.forecast import Forecast
from backend.app.db.models.record import Record
from backend.app.db.models.schedule import Schedule
from backend.app.schemas.verification import Violation

_RECORD_TYPES = {"record", "resource", "crew", "availability", "weather", "constraint"}


def _refs(schedule: Schedule) -> list[dict[str, Any]]:
    """Read input refs from solver metadata without trusting its shape."""
    values = schedule.solver_meta.get("input_versions", [])
    return values if isinstance(values, list) else []


def _record_version(db: Session, record_id: uuid.UUID) -> int | None:
    """Resolve the newest record in a supersession chain, guarding malformed cycles."""
    record = db.get(Record, record_id)
    if record is None:
        return None
    seen: set[uuid.UUID] = set()
    while record.superseded_by is not None:
        if record.id in seen:
            return None
        seen.add(record.id)
        successor = db.get(Record, record.superseded_by)
        if successor is None:
            return None
        record = successor
    return record.version


def _current_version(
    db: Session, input_type: str, input_id: uuid.UUID
) -> int | None:
    """Resolve the current logical version of one persisted dependency."""
    if input_type in _RECORD_TYPES:
        return _record_version(db, input_id)
    if input_type == "forecast":
        forecast = db.get(Forecast, input_id)
        if forecast is None:
            return None
        return db.scalar(
            select(Forecast.version)
            .where(Forecast.target == forecast.target)
            .order_by(Forecast.version.desc(), Forecast.created_at.desc(), Forecast.id)
            .limit(1)
        )
    if input_type == "schedule":
        schedule = db.get(Schedule, input_id)
        return schedule.version if schedule is not None else None
    return None


def check_versions(db: Session, schedule: Schedule) -> list[Violation]:
    """Find missing, malformed, or stale versioned inputs in schedule provenance.

    Args:
        db: Active synchronous database session.
        schedule: Persisted schedule and its captured input version list.

    Returns:
        Version-provenance violations suitable for INVALID verification outcomes.
    """
    violations: list[Violation] = []
    for reference in _refs(schedule):
        if not isinstance(reference, dict):
            violations.append(
                Violation(
                    rule="input_version",
                    message="Schedule input-version entry is malformed",
                    refs=[str(schedule.id)],
                )
            )
            continue
        try:
            input_type = str(reference["input_type"])
            input_id = uuid.UUID(str(reference["input_id"]))
            expected = int(reference["input_version"])
        except (KeyError, TypeError, ValueError):
            violations.append(
                Violation(
                    rule="input_version",
                    message="Schedule input-version entry is malformed",
                    refs=[str(schedule.id)],
                )
            )
            continue
        current = _current_version(db, input_type, input_id)
        if current is None:
            violations.append(
                Violation(
                    rule="input_missing",
                    message="A source input used by the schedule is missing or unsupported",
                    refs=[f"{input_type}:{input_id}"],
                )
            )
        elif current != expected:
            violations.append(
                Violation(
                    rule="input_version",
                    message="A source input version changed after schedule construction",
                    refs=[f"{input_type}:{input_id}:v{expected}->v{current}"],
                )
            )
    return violations


def check_forecast_link(db: Session, schedule: Schedule) -> list[Violation]:
    """Validate that forecast metadata and forecast input refs agree and resolve."""
    metadata = schedule.solver_meta
    forecast_meta = metadata.get("forecast_meta", {})
    expected_id = metadata.get("forecast_id")
    if not expected_id and isinstance(forecast_meta, dict):
        expected_id = forecast_meta.get("forecast_id")
    forecast_refs = [
        ref
        for ref in _refs(schedule)
        if isinstance(ref, dict) and ref.get("input_type") == "forecast"
    ]
    violations: list[Violation] = []
    if expected_id is None:
        if forecast_refs:
            expected_id = forecast_refs[0].get("input_id")
        else:
            return violations
    try:
        forecast_id = uuid.UUID(str(expected_id))
    except (TypeError, ValueError):
        return [
            Violation(
                rule="forecast_link",
                message="Schedule forecast link is malformed",
                refs=[str(expected_id)],
            )
        ]
    if not any(str(ref.get("input_id")) == str(forecast_id) for ref in forecast_refs):
        violations.append(
            Violation(
                rule="forecast_link",
                message="Forecast metadata is not represented in schedule input versions",
                refs=[str(forecast_id)],
            )
        )
    if db.get(Forecast, forecast_id) is None:
        violations.append(
            Violation(
                rule="forecast_missing",
                message="Schedule references a forecast that does not exist",
                refs=[str(forecast_id)],
            )
        )
    return violations


def check_evidence_links(db: Session, schedule: Schedule) -> list[Violation]:
    """Ensure source records and optional evidence references resolve in storage."""
    violations: list[Violation] = []
    for reference in _refs(schedule):
        if not isinstance(reference, dict):
            continue
        input_type = reference.get("input_type")
        if input_type not in _RECORD_TYPES:
            continue
        try:
            record_id = uuid.UUID(str(reference["input_id"]))
        except (KeyError, TypeError, ValueError):
            continue
        record = db.get(Record, record_id)
        if record is None:
            violations.append(
                Violation(
                    rule="evidence_missing",
                    message="Schedule record evidence link does not resolve",
                    refs=[str(record_id)],
                )
            )

    extra_refs = schedule.solver_meta.get("evidence_refs", [])
    if isinstance(extra_refs, list):
        for reference in extra_refs:
            if not isinstance(reference, dict):
                violations.append(
                    Violation(
                        rule="evidence_link",
                        message="Schedule evidence reference is malformed",
                        refs=[str(schedule.id)],
                    )
                )
                continue
            try:
                kind = str(reference["kind"])
                evidence_id = uuid.UUID(str(reference["id"]))
                version = int(reference["version"])
            except (KeyError, TypeError, ValueError):
                violations.append(
                    Violation(
                        rule="evidence_link",
                        message="Schedule evidence reference is malformed",
                        refs=[str(schedule.id)],
                    )
                )
                continue
            if kind in _RECORD_TYPES:
                record_evidence = db.get(Record, evidence_id)
                evidence_exists = (
                    record_evidence is not None and record_evidence.version == version
                )
            elif kind == "forecast":
                forecast_evidence = db.get(Forecast, evidence_id)
                evidence_exists = (
                    forecast_evidence is not None and forecast_evidence.version == version
                )
            else:
                evidence_exists = False
            if not evidence_exists:
                violations.append(
                    Violation(
                        rule="evidence_link",
                        message=(
                            "Schedule evidence reference does not resolve "
                            "at its recorded version"
                        ),
                        refs=[f"{kind}:{evidence_id}:v{version}"],
                    )
                )

    return violations
