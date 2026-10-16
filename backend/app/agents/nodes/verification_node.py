"""Authoritative F9 verification node; accepts no model-generated verdict input."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.agents.nodes.common import step
from backend.app.agents.state import AgentState, current_session
from backend.app.core.enums import VerificationOutcome
from backend.app.core.exceptions import RequestValidationFailed
from backend.app.services.verification.verification_service import run_checks


def run(state: AgentState, db: Session | None = None) -> AgentState:
    """Load the scheduled target from the DB and trust only deterministic F9 output."""
    if state.schedule_id is None:
        raise RequestValidationFailed("Verification node requires a persisted schedule id")
    result = run_checks(current_session(db), "schedule", state.schedule_id, state.actor)
    outcome = VerificationOutcome(result.outcome)
    return state.model_copy(
        update={
            "verification": outcome,
            "verification_id": result.id,
            "steps": step(
                state,
                "verify",
                outcome.value,
                verification_result_id=str(result.id),
                violation_count=len(result.violations),
                uncertainty_flag_count=len(result.uncertainty_flags),
            ),
        }
    )
