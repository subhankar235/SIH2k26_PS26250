"""Register versioned decisions with assumptions and input dependencies."""

from __future__ import annotations

import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from backend.app.core.enums import SourceType, ValidityStatus
from backend.app.core.exceptions import ConflictError, NotFoundError, RequestValidationFailed
from backend.app.db.models.approval import VerificationResult
from backend.app.db.models.decision import Assumption, Decision, Dependency
from backend.app.db.models.forecast import Forecast
from backend.app.db.models.record import Record
from backend.app.db.models.schedule import Schedule
from backend.app.schemas.validity import (
    AssumptionIn,
    AssumptionOut,
    DependencyOut,
    InputRef,
    ValidityEnvelope,
    VerificationSummary,
)
from backend.app.services.audit.audit_service import record as audit_record
from backend.app.services.ingestion.normaliser import to_utc
from backend.app.services.validity.input_versions import current_input_version


def _validate_input(db: Session, item: InputRef) -> bool:
    """Validate a persisted input reference and report whether it is current."""
    record_types = {"record", *(source.value for source in SourceType)}
    if item.input_type in record_types:
        persisted_record = db.get(Record, item.input_id)
        if persisted_record is None:
            raise NotFoundError(
                "Decision input not found",
                {"input_type": item.input_type, "input_id": str(item.input_id)},
            )
        if item.input_type != "record" and persisted_record.source_type != item.input_type:
            raise ConflictError(
                "Input type does not match the persisted record source type",
                {"input_type": item.input_type, "source_type": persisted_record.source_type},
            )
        row_version = persisted_record.version
    elif item.input_type == "forecast":
        persisted_forecast = db.get(Forecast, item.input_id)
        if persisted_forecast is None:
            raise NotFoundError("Forecast input not found", {"input_id": str(item.input_id)})
        row_version = persisted_forecast.version
    elif item.input_type == "schedule":
        persisted_schedule = db.get(Schedule, item.input_id)
        if persisted_schedule is None:
            raise NotFoundError("Schedule input not found", {"input_id": str(item.input_id)})
        row_version = persisted_schedule.version
    else:
        raise RequestValidationFailed(
            "Unsupported decision input type", {"input_type": item.input_type}
        )
    if row_version != item.input_version:
        raise ConflictError(
            "Decision input version does not match the referenced persisted version",
            {
                "input_type": item.input_type,
                "input_id": str(item.input_id),
                "persisted_version": row_version,
                "provided_version": item.input_version,
            },
        )
    latest_version = current_input_version(db, item.input_type, item.input_id)
    return latest_version == item.input_version


def register_decision(
    db: Session,
    decision_type: str,
    ref_id: uuid.UUID,
    inputs: list[InputRef],
    assumptions: list[AssumptionIn],
) -> Decision:
    """Create a new decision version and attach its assumptions and inputs.

    Args:
        db: Active synchronous database session.
        decision_type: Domain type of the decision.
        ref_id: UUID of the schedule, forecast, or other source result.
        inputs: Versioned input references used to make the decision.
        assumptions: Assumptions that explain decision conditions.

    Returns:
        The flushed decision in its initial uncertain state.

    Raises:
        ValueError: If an input version is less than one.
        NotFoundError: If a supported persisted input does not exist.
        ConflictError: If the input version is stale or its source type mismatches.
        RequestValidationFailed: If an input type is unsupported.
        SQLAlchemyError: If the decision graph cannot be persisted.
    """
    if any(item.input_version < 1 for item in inputs):
        raise ValueError("input versions must be positive")
    unique_inputs: dict[tuple[str, uuid.UUID], InputRef] = {}
    versions_by_id: dict[tuple[str, uuid.UUID], int] = {}
    current_inputs: list[bool] = []
    for item in inputs:
        canonical_type = (
            "record"
            if item.input_type in {source.value for source in SourceType}
            else item.input_type
        )
        key = (canonical_type, item.input_id)
        previous_version = versions_by_id.get(key)
        if previous_version is not None and previous_version != item.input_version:
            raise ConflictError(
                "Decision registration contains conflicting versions for one input",
                {"input_id": str(item.input_id)},
            )
        versions_by_id[key] = item.input_version
        previous = unique_inputs.get(key)
        if previous is not None:
            continue
        unique_inputs[key] = item
        current_inputs.append(_validate_input(db, item))
    normalized_inputs = list(unique_inputs.values())
    latest_version = db.scalar(
        select(func.max(Decision.version)).where(
            Decision.decision_type == decision_type,
            Decision.ref_id == ref_id,
        )
    )
    decision = Decision(
        decision_type=decision_type,
        ref_id=ref_id,
        status=(
            ValidityStatus.UNCERTAIN.value if all(current_inputs) else ValidityStatus.STALE.value
        ),
        version=(latest_version or 0) + 1,
    )
    db.add(decision)
    db.flush()

    assumption_rows: list[Assumption] = []
    for assumption_input in assumptions:
        row = Assumption(
            decision_id=decision.id,
            description=assumption_input.description,
            parameters=assumption_input.parameters,
        )
        db.add(row)
        assumption_rows.append(row)
    dependency_rows = [
        Dependency(
            decision_id=decision.id,
            input_type=item.input_type,
            input_id=item.input_id,
            input_version=item.input_version,
        )
        for item in normalized_inputs
    ]
    db.add_all(dependency_rows)
    db.flush()

    audit_record(
        db,
        "decision",
        decision.id,
        "registered",
        None,
        {
            "decision_type": decision_type,
            "ref_id": str(ref_id),
            "version": decision.version,
            "input_count": len(dependency_rows),
            "assumption_count": len(assumption_rows),
            "status": decision.status,
        },
        "system",
    )
    for assumption in assumption_rows:
        audit_record(
            db,
            "assumption",
            assumption.id,
            "registered",
            None,
            {"decision_id": str(decision.id), "description": assumption.description},
            "system",
        )
    for dependency in dependency_rows:
        audit_record(
            db,
            "dependency",
            dependency.id,
            "registered",
            None,
            {
                "decision_id": str(decision.id),
                "input_type": dependency.input_type,
                "input_id": str(dependency.input_id),
                "input_version": dependency.input_version,
            },
            "system",
        )
    return decision


def envelope(db: Session, decision_id: uuid.UUID) -> ValidityEnvelope:
    """Return the decision's current assumptions and input-version envelope.

    Args:
        db: Active synchronous database session.
        decision_id: UUID of the decision.

    Returns:
        Decision identity, version, status, assumptions, and dependencies.

    Raises:
        NotFoundError: If the decision does not exist.
    """
    decision = db.get(Decision, decision_id)
    if decision is None:
        raise NotFoundError("Decision not found", {"id": str(decision_id)})
    assumptions = db.scalars(
        select(Assumption).where(Assumption.decision_id == decision.id).order_by(Assumption.id)
    ).all()
    dependencies = db.scalars(
        select(Dependency)
        .where(Dependency.decision_id == decision.id)
        .order_by(Dependency.input_type, Dependency.input_id, Dependency.input_version)
    ).all()
    verification = db.scalar(
        select(VerificationResult)
        .where(
            or_(
                and_(
                    VerificationResult.target_type == "decision",
                    VerificationResult.target_id == decision.id,
                ),
                and_(
                    VerificationResult.target_type == decision.decision_type,
                    VerificationResult.target_id == decision.ref_id,
                ),
            )
        )
        .order_by(VerificationResult.checked_at.desc(), VerificationResult.id)
        .limit(1)
    )
    return ValidityEnvelope(
        decision_id=decision.id,
        decision_type=decision.decision_type,
        version=decision.version,
        status=decision.status,
        assumptions=[
            AssumptionOut(
                id=item.id,
                description=item.description,
                parameters=item.parameters,
            )
            for item in assumptions
        ],
        dependencies=[
            DependencyOut(
                input_type=item.input_type,
                input_id=item.input_id,
                input_version=item.input_version,
            )
            for item in dependencies
        ],
        verification=(
            VerificationSummary(
                outcome=verification.outcome,
                checked_at=to_utc(verification.checked_at),
                violation_count=len(verification.violations),
                uncertainty_flags=verification.uncertainty_flags,
            )
            if verification is not None
            else None
        ),
    )
