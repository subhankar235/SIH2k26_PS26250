"""Persist independent verification outcomes for schedules and decisions."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.enums import VerificationOutcome
from backend.app.core.exceptions import NotFoundError, RequestValidationFailed
from backend.app.db.models.approval import VerificationResult
from backend.app.db.models.schedule import Schedule
from backend.app.services.audit.audit_service import record as audit_record
from backend.app.services.verification.approval_router import route as route_for_review
from backend.app.services.verification.consistency_checker import (
    check_evidence_links,
    check_forecast_link,
    check_versions,
)
from backend.app.services.verification.constraint_checker import (
    ProblemData,
    ScheduleData,
    check_all,
)
from backend.app.services.verification.uncertainty_flagger import flags as uncertainty_flags_for


def run_checks(
    db: Session,
    target_type: str,
    target_id: uuid.UUID,
    actor: str,
) -> VerificationResult:
    """Independently check and persist one schedule verification result.

    Args:
        db: Active synchronous database session.
        target_type: Verification target type; currently ``schedule`` is supported.
        target_id: UUID of the schedule.
        actor: Actor responsible for requesting verification.

    Returns:
        Persisted outcome with plain-Python violations and uncertainty flags.

    Raises:
        NotFoundError: If the schedule does not exist.
        RequestValidationFailed: If target type, actor, or persisted problem data is invalid.
    """
    if target_type != "schedule":
        raise RequestValidationFailed(
            "Independent checker currently supports schedule targets",
            {"target_type": target_type},
        )
    if not actor.strip():
        raise RequestValidationFailed("An actor is required to record verification")
    schedule = db.get(Schedule, target_id)
    if schedule is None:
        raise NotFoundError("Schedule not found", {"id": str(target_id)})

    problem_data = schedule.solver_meta.get("problem")
    if not isinstance(problem_data, dict):
        raise RequestValidationFailed(
            "Schedule lacks the original normalized problem required for verification",
            {"schedule_id": str(schedule.id)},
        )
    try:
        plain_problem = ProblemData(
            tasks=problem_data["tasks"],
            resources=problem_data["resources"],
            precedence=problem_data.get("precedence", []),
            policies=problem_data.get("policies", []),
            horizon=int(problem_data["horizon"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RequestValidationFailed(
            "Schedule problem snapshot is malformed", {"schedule_id": str(schedule.id)}
        ) from error

    violations = [
        *check_all(ScheduleData(schedule.assignments), plain_problem),
        *check_versions(db, schedule),
        *check_forecast_link(db, schedule),
        *check_evidence_links(db, schedule),
    ]
    uncertainty_flags = uncertainty_flags_for(
        db, schedule, get_settings().uncertainty_threshold
    )
    outcome = (
        VerificationOutcome.INVALID
        if violations
        else VerificationOutcome.UNCERTAIN
        if uncertainty_flags
        else VerificationOutcome.VERIFIED
    )
    row = VerificationResult(
        target_type=target_type,
        target_id=target_id,
        outcome=outcome.value,
        violations=[violation.model_dump(mode="json") for violation in violations],
        uncertainty_flags=[flag.model_dump(mode="json") for flag in uncertainty_flags],
    )
    db.add(row)
    db.flush()
    audit_record(
        db,
        "verification_result",
        row.id,
        "checked",
        None,
        {
            "target_type": target_type,
            "target_id": str(target_id),
            "outcome": outcome.value,
            "violation_count": len(violations),
            "uncertainty_flag_count": len(uncertainty_flags),
        },
        actor,
    )
    route_for_review(db, row)
    return row


def get(db: Session, verification_id: uuid.UUID) -> VerificationResult:
    """Return a persisted independent verification result.

    Args:
        db: Active synchronous database session.
        verification_id: UUID of the result.

    Returns:
        Verification ORM row.

    Raises:
        NotFoundError: If the result is absent.
    """
    result = db.get(VerificationResult, verification_id)
    if result is None:
        raise NotFoundError("Verification result not found", {"id": str(verification_id)})
    return result
