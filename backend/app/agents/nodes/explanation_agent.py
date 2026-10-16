"""Build and validate an evidence-grounded explanation for a verified workflow."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.agents.nodes.common import step
from backend.app.agents.state import AgentState, current_session
from backend.app.core.exceptions import RequestValidationFailed
from backend.app.schemas.agents import EvidenceRef, ExplanationOut
from backend.app.services.explanation.explainer import build_explanation
from backend.app.services.planning.solver_service import get_schedule


def run(state: AgentState, db: Session | None = None) -> AgentState:
    """Synthesize typed claims, persist them through the agent service, and resolve refs."""
    if state.schedule_id is None or state.verification_id is None or state.verification is None:
        raise RequestValidationFailed("Explanation requires a schedule and verification result")
    session = current_session(db)
    schedule = get_schedule(session, state.schedule_id)
    refs = [
        EvidenceRef(kind="schedule", id=schedule.id, version=schedule.version),
        EvidenceRef(kind="verification_result", id=state.verification_id, version=1),
    ]
    if state.evidence is not None and state.evidence.issue_ids:
        refs.append(EvidenceRef(kind="issue", id=state.evidence.issue_ids[0], version=1))
    text = (
        f"The schedule contains {len(schedule.assignments)} assignments and its independent "
        f"verification outcome is {state.verification.value} "
        f"[schedule:{schedule.id}:v{schedule.version}] "
        f"[verification_result:{state.verification_id}:v1]."
    )
    if state.evidence is not None and state.evidence.issue_ids:
        text += (
            f" Evidence analysis recorded {len(state.evidence.issue_ids)} open quality issues "
            f"[issue:{state.evidence.issue_ids[0]}:v1]."
        )
    explanation = ExplanationOut(text=text, evidence_refs=refs)

    from backend.app.services.agent_service import get_run_row, persist_explanation

    run_row = get_run_row(session, state.run_id)
    persist_explanation(session, run_row, explanation)
    validated = build_explanation(session, run_row)
    return state.model_copy(
        update={
            "explanation": validated,
            "steps": step(
                state,
                "explain",
                "completed",
                evidence_reference_count=len(validated.evidence_refs),
            ),
        }
    )
