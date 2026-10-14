"""Read-oriented validity service methods used by API routes."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.enums import ValidityStatus
from backend.app.core.exceptions import NotFoundError, RequestValidationFailed
from backend.app.db.models.decision import Decision
from backend.app.schemas.common import Page
from backend.app.schemas.validity import DecisionOut
from backend.app.services.validity.assumption_tracker import envelope


def _decision_out(db: Session, decision: Decision) -> DecisionOut:
    """Assemble the public decision schema from its ORM row and envelope."""
    validity_envelope = envelope(db, decision.id)
    return DecisionOut.model_validate(
        {
            "id": decision.id,
            "decision_type": decision.decision_type,
            "version": decision.version,
            "status": ValidityStatus(decision.status),
            "assumptions": validity_envelope.assumptions,
            "dependencies": validity_envelope.dependencies,
        }
    )


def list_decisions(
    db: Session,
    limit: int,
    offset: int,
    status: str | None = None,
) -> Page[DecisionOut]:
    """Return a filtered, paginated list of decision validity envelopes.

    Args:
        db: Active synchronous database session.
        limit: Maximum result count.
        offset: Number of matching decisions to skip.
        status: Optional validity status filter.

    Returns:
        Page of decisions with assumptions and dependencies.

    Raises:
        RequestValidationFailed: If status or pagination values are invalid.
        SQLAlchemyError: If decisions cannot be queried.
    """
    if limit < 1 or offset < 0:
        raise RequestValidationFailed("limit must be positive and offset non-negative")
    if status is not None:
        try:
            status = ValidityStatus(status).value
        except ValueError as error:
            raise RequestValidationFailed("Unknown validity status", {"status": status}) from error
    filters = [Decision.status == status] if status is not None else []
    total = db.scalar(select(func.count()).select_from(Decision).where(*filters)) or 0
    decisions = db.scalars(
        select(Decision)
        .where(*filters)
        .order_by(Decision.created_at.desc(), Decision.version.desc(), Decision.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return Page[DecisionOut](
        items=[_decision_out(db, decision) for decision in decisions],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_decision(db: Session, decision_id: UUID) -> DecisionOut:
    """Return one decision with its validity envelope.

    Args:
        db: Active synchronous database session.
        decision_id: UUID of the decision.

    Returns:
        The decision response.

    Raises:
        NotFoundError: If the decision does not exist.
    """
    decision = db.get(Decision, decision_id)
    if decision is None:
        raise NotFoundError("Decision not found", {"id": str(decision_id)})
    return _decision_out(db, decision)
