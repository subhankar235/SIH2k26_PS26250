"""Integration guard preventing approval of a non-verified target."""

from __future__ import annotations

from uuid import uuid4

import pytest

from backend.app.core.enums import ApprovalDecision
from backend.app.core.exceptions import ConflictError
from backend.app.core.security import Actor
from backend.app.db.models import Approval, VerificationResult
from backend.app.services.verification.approval_router import decide


def test_uncertain_verification_cannot_be_approved(db) -> None:
    """Persist a queue item and require the authoritative outcome to be VERIFIED."""
    result = VerificationResult(
        target_type="schedule",
        target_id=uuid4(),
        outcome="uncertain",
        violations=[],
        uncertainty_flags=[{"code": "STALE_INPUT", "message": "input changed"}],
    )
    db.add(result)
    db.flush()

    with pytest.raises(ConflictError, match="only when its latest verification is VERIFIED"):
        decide(
            db,
            result.id,
            ApprovalDecision.APPROVED,
            "Approve this uncertain schedule.",
            Actor(id="approver-test", role="approver"),
        )

    assert db.query(Approval).count() == 0
