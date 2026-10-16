"""Derive a human-review queue from verification results and record decisions."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.enums import ApprovalDecision, VerificationOutcome
from backend.app.core.exceptions import ConflictError, NotFoundError, RequestValidationFailed
from backend.app.core.security import Actor
from backend.app.db.models.approval import Approval, VerificationResult
from backend.app.schemas.approvals import ApprovalQueueItem
from backend.app.schemas.common import Page
from backend.app.services.audit.audit_service import record as audit_record


def _queue_item(result: VerificationResult) -> ApprovalQueueItem:
    """Project a persisted verification result to its compact queue item."""
    outcome = VerificationOutcome(result.outcome)
    return ApprovalQueueItem(
        id=result.id,
        target_type=result.target_type,
        target_id=result.target_id,
        outcome=outcome,
        queued_at=result.checked_at,
        summary={
            "violation_count": len(result.violations),
            "uncertainty_flag_count": len(result.uncertainty_flags),
            "verification_result_id": str(result.id),
        },
    )


def route(
    db: Session, result: VerificationResult
) -> ApprovalQueueItem | None:
    """Route a verified or uncertain result to the dynamically derived review queue.

    The queue is derived from verification rows because the persisted ``approval``
    table represents final human decisions, not pending requests.

    Args:
        db: Active synchronous database session.
        result: Newly persisted verification result.

    Returns:
        Queue item for VERIFIED/UNCERTAIN results, otherwise None.
    """
    del db
    if result.outcome not in {
        VerificationOutcome.VERIFIED.value,
        VerificationOutcome.UNCERTAIN.value,
    }:
        return None
    return _queue_item(result)


def queue(db: Session, limit: int, offset: int) -> Page[ApprovalQueueItem]:
    """Page latest VERIFIED/UNCERTAIN target results not yet decided by a human."""
    if limit < 1 or offset < 0:
        raise RequestValidationFailed("Approval queue pagination is invalid")
    all_results = list(
        db.scalars(
            select(VerificationResult).order_by(
                VerificationResult.checked_at.desc(), VerificationResult.id.desc()
            )
        ).all()
    )
    latest_by_target: dict[tuple[str, UUID], VerificationResult] = {}
    for item in all_results:
        latest_by_target.setdefault((item.target_type, item.target_id), item)
    pending = [
        item
        for item in latest_by_target.values()
        if item.outcome in {VerificationOutcome.VERIFIED.value, VerificationOutcome.UNCERTAIN.value}
    ]
    approvals = db.scalars(select(Approval)).all()
    decided_after = {
        (item.target_type, item.target_id): item.decided_at
        for item in approvals
    }
    pending = [
        item
        for item in pending
        if decided_after.get((item.target_type, item.target_id)) is None
        or item.checked_at > decided_after[(item.target_type, item.target_id)]
    ]
    pending.sort(key=lambda item: (item.checked_at, str(item.id)), reverse=True)
    total = len(pending)
    return Page[ApprovalQueueItem](
        items=[_queue_item(item) for item in pending[offset : offset + limit]],
        total=total,
        limit=limit,
        offset=offset,
    )


def decide(
    db: Session,
    approval_id: UUID,
    decision: ApprovalDecision,
    rationale: str,
    actor: Actor,
) -> Approval:
    """Persist a human decision, permitting approval only for the latest VERIFIED result.

    ``approval_id`` is the queue item's verification-result UUID as returned by
    :func:`route` and :func:`queue`.
    """
    result = db.get(VerificationResult, approval_id)
    if result is None:
        raise NotFoundError("Approval queue item not found", {"id": str(approval_id)})
    normalized_decision = ApprovalDecision(decision)
    normalized_rationale = rationale.strip()
    if len(normalized_rationale) < 10:
        raise RequestValidationFailed("Approval rationale must contain at least 10 characters")
    if len(normalized_rationale) > 4000:
        raise RequestValidationFailed("Approval rationale must not exceed 4000 characters")
    latest = db.scalar(
        select(VerificationResult)
        .where(
            VerificationResult.target_type == result.target_type,
            VerificationResult.target_id == result.target_id,
        )
        .order_by(VerificationResult.checked_at.desc(), VerificationResult.id.desc())
        .limit(1)
    )
    if latest is None or latest.id != result.id:
        raise ConflictError("Approval queue item is no longer the latest verification result")
    if (
        normalized_decision == ApprovalDecision.APPROVED
        and latest.outcome != VerificationOutcome.VERIFIED.value
    ):
        raise ConflictError(
            "A target may be approved only when its latest verification is VERIFIED",
            {"target_type": result.target_type, "target_id": str(result.target_id)},
        )
    if normalized_decision == ApprovalDecision.REJECTED and latest.outcome not in {
        VerificationOutcome.VERIFIED.value,
        VerificationOutcome.UNCERTAIN.value,
        VerificationOutcome.INVALID.value,
    }:
        raise ConflictError("This verification result is not eligible for human review")
    previous = db.scalar(
        select(Approval)
        .where(
            Approval.target_type == result.target_type,
            Approval.target_id == result.target_id,
        )
        .order_by(Approval.decided_at.desc(), Approval.id.desc())
        .limit(1)
    )
    if previous is not None and previous.decided_at >= result.checked_at:
        raise ConflictError("This verification result already has a human decision")

    approval = Approval(
        target_type=result.target_type,
        target_id=result.target_id,
        approver=actor.id,
        decision=normalized_decision.value,
        rationale=normalized_rationale,
        decided_at=datetime.now(UTC),
    )
    db.add(approval)
    db.flush()
    audit_record(
        db,
        "approval",
        approval.id,
        "decided",
        None,
        {
            "target_type": approval.target_type,
            "target_id": str(approval.target_id),
            "verification_result_id": str(result.id),
            "decision": approval.decision,
            "approver": approval.approver,
            "rationale": approval.rationale,
            "decided_at": approval.decided_at.isoformat(),
        },
        actor.id,
    )
    return approval
