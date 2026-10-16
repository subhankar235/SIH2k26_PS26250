"""Checkpoint-aware human approval interrupt node."""

from __future__ import annotations

from langgraph.types import interrupt

from backend.app.agents.state import AgentState, current_session
from backend.app.core.enums import AgentRunStatus, ApprovalDecision
from backend.app.schemas.agents import AgentStep


def _record_decision(state: AgentState, decision: ApprovalDecision, actor_id: str) -> None:
    """Delegate human decision persistence to the F9 approval service."""
    from backend.app.core.security import Actor
    from backend.app.services.verification.approval_router import decide as record_approval

    if state.verification_id is None:
        return
    rationale = (
        "Human approved the verified agent workflow result."
        if decision == ApprovalDecision.APPROVED
        else "Human rejected the agent workflow recommendation."
    )
    record_approval(
        current_session(),
        state.verification_id,
        decision,
        rationale,
        Actor(id=actor_id, role="approver"),
    )


def approval_interrupt(state: AgentState) -> AgentState:
    """Persist an awaiting-approval state, interrupt, and resume after a human decision."""
    waiting = state.model_copy(update={"status": AgentRunStatus.AWAITING_APPROVAL})
    from backend.app.services.agent_service import persist_state

    persist_state(current_session(), waiting, status=AgentRunStatus.AWAITING_APPROVAL)
    choice = interrupt(
        {
            "run_id": str(state.run_id),
            "schedule_id": str(state.schedule_id) if state.schedule_id else None,
            "verification": state.verification.value if state.verification else None,
            "verification_id": str(state.verification_id) if state.verification_id else None,
        }
    )
    actor_id = state.actor
    choice_value = choice
    if isinstance(choice, dict):
        choice_value = choice.get("decision")
        actor_id = str(choice.get("actor", actor_id))
    try:
        decision = ApprovalDecision(choice_value)
    except (TypeError, ValueError) as error:
        raise ValueError("Human approval resume value must be approved or rejected") from error
    if decision == ApprovalDecision.APPROVED:
        if state.verification != "verified":
            raise ValueError("Only a VERIFIED agent result can be approved")
        _record_decision(state, decision, actor_id)
        final_status = AgentRunStatus.COMPLETED
    else:
        _record_decision(state, decision, actor_id)
        final_status = AgentRunStatus.FAILED
    return state.model_copy(
        update={
            "status": final_status,
            "steps": [
                *state.steps,
                AgentStep(
                    name="human_approval",
                    status=decision.value,
                    details={
                        "verification": (
                            state.verification.value if state.verification else None
                        )
                    },
                ),
            ],
        }
    )
