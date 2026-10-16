"""Enforce validity-status transitions and evaluate check results."""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from backend.app.core.enums import ValidityStatus
from backend.app.core.exceptions import ConflictError, NotFoundError, RequestValidationFailed
from backend.app.db.models.decision import Decision
from backend.app.schemas.validity import CheckResult
from backend.app.services.audit.audit_service import record as audit_record

_NONTERMINAL_TARGETS = {ValidityStatus.STALE, ValidityStatus.UNCERTAIN}


def transition(
    db: Session,
    decision: Decision,
    new: ValidityStatus,
    reason: str,
    actor: str,
) -> Decision:
    """Apply one allowed validity transition and audit it in the same transaction.

    Args:
        db: Active synchronous database session.
        decision: Decision to transition.
        new: Requested next validity state.
        reason: Short explanation recorded in the audit diff.
        actor: Actor responsible for the transition.

    Returns:
        The updated decision with its version incremented.

    Raises:
        ConflictError: If the transition is not allowed by the validity state machine.
        NotFoundError: If the decision no longer exists.
        RequestValidationFailed: If the reason, actor, or target status is invalid.
        SQLAlchemyError: If the atomic status/audit transaction cannot be completed.
    """
    if not isinstance(reason, str) or not isinstance(actor, str):
        raise RequestValidationFailed("Reason and actor must be strings")
    normalized_reason = reason.strip()
    normalized_actor = actor.strip()
    if not normalized_reason:
        raise RequestValidationFailed("A non-empty reason is required for a validity transition")
    if not normalized_actor:
        raise RequestValidationFailed("An actor is required for a validity transition")

    expected_version = decision.version
    expected_status = decision.status
    persisted = db.scalar(
        select(Decision)
        .where(Decision.id == decision.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if persisted is None:
        raise NotFoundError("Decision not found", {"id": str(decision.id)})
    if persisted.version != expected_version or persisted.status != expected_status:
        raise ConflictError(
            "Decision changed after it was loaded",
            {"decision_id": str(decision.id), "current_version": persisted.version},
        )
    decision = persisted
    try:
        current = ValidityStatus(decision.status)
    except ValueError as error:
        raise ConflictError(
            "Decision has an unsupported validity status",
            {"decision_id": str(decision.id), "status": str(decision.status)},
        ) from error
    try:
        target = ValidityStatus(new)
    except ValueError as error:
        raise RequestValidationFailed("Unsupported target validity status") from error
    new = target
    if current == new:
        return decision
    if current == ValidityStatus.INVALIDATED:
        raise ConflictError(
            "Invalidated decisions are terminal; register a new decision version",
            {"decision_id": str(decision.id)},
        )
    allowed = new in _NONTERMINAL_TARGETS or (
        current == ValidityStatus.STALE
        and new in {ValidityStatus.VERIFIED, ValidityStatus.INVALIDATED}
    )
    if not allowed:
        raise ConflictError(
            "Validity transition is not allowed",
            {"from": current.value, "to": new.value, "decision_id": str(decision.id)},
        )

    old_version = decision.version
    new_version = old_version + 1
    with db.begin_nested():
        result = cast(
            CursorResult[Any],
            db.execute(
                update(Decision)
                .where(
                    Decision.id == decision.id,
                    Decision.version == old_version,
                    Decision.status == current.value,
                )
                .values(status=new.value, version=Decision.version + 1)
                .execution_options(synchronize_session=False)
            ),
        )
        if result.rowcount != 1:
            raise ConflictError(
                "Decision changed concurrently during validity transition",
                {"decision_id": str(decision.id), "version": old_version},
            )
        audit_record(
            db,
            "decision",
            decision.id,
            "validity_transition",
            {"status": current.value, "version": old_version},
            {"status": new.value, "version": new_version, "reason": normalized_reason},
            normalized_actor,
        )
    set_committed_value(decision, "status", new.value)
    set_committed_value(decision, "version", new_version)
    return decision


def evaluate(decision: Decision, check_results: list[CheckResult]) -> ValidityStatus:
    """Determine a decision status from independent verification checks.

    Args:
        decision: Decision being evaluated; included for a stable service contract.
        check_results: Results of authoritative validity and verification checks.

    Returns:
        FAILED/contradictory required checks take precedence and return INVALIDATED; missing
        required checks, uncertain checks, or no required checks return UNCERTAIN; VERIFIED
        requires at least one complete required check and all required checks passing.

    Raises:
        None.
    """
    del decision
    checks_by_name: dict[str, list[CheckResult]] = {}
    for result in check_results:
        checks_by_name.setdefault(result.name, []).append(result)

    # A failed required check or contradictory reports from a required check
    # invalidate first, even if other required checks are still incomplete.
    for results in checks_by_name.values():
        required_results = [result for result in results if result.required]
        outcomes = {result.valid for result in required_results if result.valid is not None}
        if (
            any(result.valid is False or result.contradictory for result in required_results)
            or len(outcomes) > 1
        ):
            return ValidityStatus.INVALIDATED

    if any(
        not result.complete or result.valid is None for result in check_results if result.required
    ):
        return ValidityStatus.UNCERTAIN
    if any(result.valid is False or result.uncertain for result in check_results):
        return ValidityStatus.UNCERTAIN
    if not check_results:
        return ValidityStatus.UNCERTAIN
    if not any(result.required for result in check_results):
        return ValidityStatus.UNCERTAIN
    if any(result.valid is not True for result in check_results if result.required):
        return ValidityStatus.UNCERTAIN
    if any(result.uncertain for result in check_results):
        return ValidityStatus.UNCERTAIN
    return ValidityStatus.VERIFIED
