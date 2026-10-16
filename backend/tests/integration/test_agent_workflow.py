"""Integration coverage for the checkpointed, typed F8 agent graph."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.agents.graph import invoke_graph
from backend.app.agents.retry import (
    changed_since_last,
    next_attempt,
    parse_output_with_retry,
)
from backend.app.agents.routing import route_after_verify
from backend.app.agents.state import AgentState
from backend.app.core.enums import AgentRunStatus, ApprovalDecision, VerificationOutcome
from backend.app.core.exceptions import ConflictError
from backend.app.db.base import Base
from backend.app.db.models import AgentRun, Approval, AuditEntry, Decision, Schedule
from backend.app.schemas.agents import AgentRequestIn
from backend.app.services.agent_service import resume


def test_route_and_retry_are_bounded_and_identical_attempts_escalate() -> None:
    """Route by authoritative outcomes, bound attempts, and fingerprint inputs only."""
    request = AgentRequestIn(request={"problem": {}}, seed=5)
    state = AgentState(
        run_id=uuid4(),
        request=request,
        verification=VerificationOutcome.INVALID,
    )
    assert route_after_verify(state) == "reanalyse"
    retried = next_attempt(state, max_retries=2)
    assert retried.retries == 1
    assert changed_since_last(retried, retried.last_attempt_fingerprint or "") is False
    assert route_after_verify(retried) == "escalate"
    verified = state.model_copy(update={"verification": VerificationOutcome.VERIFIED})
    assert route_after_verify(verified) == "explain"
    exhausted = next_attempt(retried.model_copy(update={"retries": 2}), max_retries=2)
    assert exhausted.status == AgentRunStatus.ESCALATED


def test_schema_parse_retry_is_single_and_typed() -> None:
    """Retry one invalid provider payload and surface a second schema failure."""
    from backend.app.agents.state import ChangeAnalysisOutput

    payloads = iter([{"changes": [{"not_a_change": True}]}, {"changes": [], "uncertainty": []}])
    parsed = parse_output_with_retry(lambda: next(payloads), ChangeAnalysisOutput)
    assert parsed.changes == []
    assert parsed.uncertainty == []

    calls = 0

    def invalid_output():
        nonlocal calls
        calls += 1
        return {"changes": [{"input_type": "record"}]}

    with pytest.raises(ValueError):
        parse_output_with_retry(invalid_output, ChangeAnalysisOutput)
    assert calls == 2


def test_full_agent_graph_checkpoints_and_requires_human_approval() -> None:
    """Run evidence through verification, interrupt for approval, then resume safely."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as db:
            request = AgentRequestIn(
                request={
                    "problem": {
                        "tasks": [
                            {
                                "id": "task-a",
                                "duration": 2,
                                "resource_type": "crew",
                                "earliest": 0,
                                "latest": 4,
                            }
                        ],
                        "resources": [
                            {
                                "id": "crew-a",
                                "type": "crew",
                                "capacity": 1,
                                "available": [[0, 8]],
                            }
                        ],
                        "windows": {"horizon": 8},
                        "precedence": [],
                        "policies": [],
                        "objectives": {"makespan": 1.0},
                    },
                    "time_limit_s": 2,
                },
                seed=23,
            )
            run_id = uuid4()
            state = AgentState(run_id=run_id, request=request, actor="planner")
            run = AgentRun(
                id=run_id,
                request=request.model_dump(mode="json"),
                graph_state=state.model_dump(mode="json"),
                checkpoints=[],
                retries=0,
                status=AgentRunStatus.RUNNING.value,
                explanation={},
            )
            db.add(run)
            db.flush()

            paused, interrupted = invoke_graph(db, state)
            assert interrupted is True
            assert paused.verification == VerificationOutcome.VERIFIED
            assert paused.explanation is not None
            assert run.status == AgentRunStatus.AWAITING_APPROVAL.value
            assert {step.name for step in paused.steps} >= {
                "evidence",
                "prediction",
                "change_analysis",
                "optimise",
                "verify",
                "explain",
            }
            db.commit()

            completed = resume(
                db,
                run_id,
                ApprovalDecision.APPROVED,
                actor="reviewer-1",
            )
            assert completed.status == AgentRunStatus.COMPLETED.value
            schedule_id = UUID(completed.graph_state["schedule_id"])
            schedule = db.get(Schedule, schedule_id)
            assert schedule is not None and schedule.status == "verified"
            assert len(db.scalars(select(Approval)).all()) == 1
            assert db.scalars(
                select(Decision).where(Decision.ref_id == schedule.id)
            ).first() is not None
            actions = db.scalars(
                select(AuditEntry.action).where(AuditEntry.entity_id == run_id)
            ).all()
            assert "explanation_created" in actions
            assert "human_resumed" in actions

            with pytest.raises(ConflictError, match="not waiting"):
                resume(db, run_id, ApprovalDecision.APPROVED, actor="reviewer-1")
    finally:
        engine.dispose()
