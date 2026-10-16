"""Surface unresolved forecast, evidence, and decision uncertainty for review."""

from __future__ import annotations

import math
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.claim import Claim, Issue
from backend.app.db.models.decision import Decision
from backend.app.db.models.forecast import Forecast
from backend.app.db.models.record import Record
from backend.app.db.models.schedule import Schedule
from backend.app.schemas.verification import UncertaintyFlag
from backend.app.services.verification.consistency_checker import check_versions


def _record_refs(schedule: Schedule) -> set[uuid.UUID]:
    """Parse input record ids captured with a schedule."""
    result: set[uuid.UUID] = set()
    references = schedule.solver_meta.get("input_versions", [])
    if not isinstance(references, list):
        return result
    for reference in references:
        if not isinstance(reference, dict) or reference.get("input_type") not in {
            "record",
            "resource",
            "crew",
            "availability",
            "weather",
            "constraint",
        }:
            continue
        try:
            result.add(uuid.UUID(str(reference["input_id"])))
        except (KeyError, TypeError, ValueError):
            continue
    return result


def _forecast_refs(schedule: Schedule) -> list[uuid.UUID]:
    """Parse forecast ids from input refs and forecast metadata."""
    result: set[uuid.UUID] = set()
    references = schedule.solver_meta.get("input_versions", [])
    if isinstance(references, list):
        for reference in references:
            if isinstance(reference, dict) and reference.get("input_type") == "forecast":
                try:
                    result.add(uuid.UUID(str(reference["input_id"])))
                except (KeyError, TypeError, ValueError):
                    continue
    forecast_meta = schedule.solver_meta.get("forecast_meta", {})
    if isinstance(forecast_meta, dict) and forecast_meta.get("forecast_id"):
        try:
            result.add(uuid.UUID(str(forecast_meta["forecast_id"])))
        except ValueError:
            pass
    return sorted(result, key=str)


def _forecast_is_high(forecast: Forecast, threshold: float) -> bool:
    """Compare forecast flag and interval width to the configured relative threshold."""
    if forecast.high_uncertainty:
        return True
    if not forecast.points:
        return False
    scale_value = forecast.calibration_meta.get("target_scale", 0.0)
    try:
        target_scale = float(scale_value)
    except (TypeError, ValueError):
        target_scale = 0.0
    maximum = 0.0
    for point in forecast.points:
        try:
            mean = float(point["mean"])
            lower = float(point["lower"])
            upper = float(point["upper"])
        except (KeyError, TypeError, ValueError):
            return True
        if not all(math.isfinite(value) for value in (mean, lower, upper)) or upper < lower:
            return True
        scale = max(abs(mean), target_scale)
        width = (upper - lower) / scale if scale else (0.0 if upper == lower else math.inf)
        maximum = max(maximum, width)
    return maximum > threshold


def flags(db: Session, schedule: Schedule, threshold: float) -> list[UncertaintyFlag]:
    """Return high-forecast, unresolved-conflict, uncertain-decision, and stale-input flags.

    Args:
        db: Active synchronous database session.
        schedule: Persisted schedule under verification.
        threshold: Relative forecast interval-width threshold in [0, 1] or larger.

    Returns:
        Deduplicated uncertainty flags with database references.

    Raises:
        ValueError: If threshold is negative or non-finite.
    """
    if not math.isfinite(threshold) or threshold < 0:
        raise ValueError("uncertainty threshold must be finite and non-negative")
    result: list[UncertaintyFlag] = []
    for forecast_id in _forecast_refs(schedule):
        forecast = db.get(Forecast, forecast_id)
        if forecast is not None and _forecast_is_high(forecast, threshold):
            result.append(
                UncertaintyFlag(
                    code="HIGH_FORECAST_UNCERTAINTY",
                    message="Forecast uncertainty exceeds the configured planning threshold",
                    refs=[f"forecast:{forecast.id}:v{forecast.version}"],
                )
            )

    record_ids = _record_refs(schedule)
    entity_ids: set[str] = set()
    for record_id in record_ids:
        record = db.get(Record, record_id)
        if record is not None:
            entity_ids.add(record.entity_id)
    active_claim_ids = {
        str(claim_id)
        for claim_id in db.scalars(
            select(Claim.id)
            .join(Record, Claim.record_id == Record.id)
            .where(Record.id.in_(record_ids), Claim.superseded_by.is_(None))
        ).all()
    } if record_ids else set()
    for issue in db.scalars(
        select(Issue)
        .where(Issue.status == "open", Issue.issue_class.in_(["conflict", "duplicate"]))
        .order_by(Issue.detected_at, Issue.id)
    ):
        details = issue.details if isinstance(issue.details, dict) else {}
        issue_entity = details.get("entity_id")
        issue_claims = {str(item) for item in issue.claim_ids}
        referenced = issue_entity in entity_ids or bool(issue_claims & active_claim_ids)
        explicit_record = details.get("record_id")
        if explicit_record:
            try:
                referenced = referenced or uuid.UUID(str(explicit_record)) in record_ids
            except ValueError:
                pass
        if referenced:
            result.append(
                UncertaintyFlag(
                    code="UNRESOLVED_CONFLICT",
                    message="Schedule evidence has an unresolved conflict or duplicate issue",
                    refs=[f"issue:{issue.id}"],
                )
            )

    decision = db.scalar(
        select(Decision)
        .where(Decision.decision_type == "schedule", Decision.ref_id == schedule.id)
        .order_by(Decision.version.desc(), Decision.created_at.desc(), Decision.id)
        .limit(1)
    )
    if decision is not None and decision.status in {"stale", "uncertain"}:
        result.append(
            UncertaintyFlag(
                code="DECISION_UNCERTAIN",
                message="The schedule decision validity is not currently verified",
                refs=[f"decision:{decision.id}:v{decision.version}"],
            )
        )

    for violation in check_versions(db, schedule):
        result.append(
            UncertaintyFlag(
                code="STALE_INPUT",
                message=violation.message,
                refs=violation.refs,
            )
        )
    unique: dict[tuple[str, tuple[str, ...]], UncertaintyFlag] = {}
    for item in result:
        unique[(item.code, tuple(item.refs))] = item
    return list(unique.values())
