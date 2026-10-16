"""Persist, execute, resume, and present checkpointed agent workflow runs."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session, sessionmaker

from backend.app.agents.state import AgentState
from backend.app.core.enums import AgentRunStatus, ApprovalDecision
from backend.app.core.exceptions import ConflictError, NotFoundError, RequestValidationFailed
from backend.app.db.models.agent_run import AgentRun
from backend.app.schemas.agents import AgentRequestIn, AgentRunOut, AgentStep, ExplanationOut
from backend.app.services.audit.audit_service import record as audit_record

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="agent-run")


def _to_output(run: AgentRun) -> AgentRunOut:
    """Build the public agent status response from its checkpointed state."""
    raw_steps = run.graph_state.get("steps", [])
    steps = [AgentStep.model_validate(item) for item in raw_steps if isinstance(item, dict)]
    return AgentRunOut(
        id=run.id,
        status=AgentRunStatus(run.status),
        steps=steps,
        retries=max(0, int(run.retries)),
    )


def get_run_row(db: Session, run_id: UUID) -> AgentRun:
    """Load an agent run ORM row for internal service-to-service composition."""
    run = db.get(AgentRun, run_id)
    if run is None:
        raise NotFoundError("Agent run not found", {"id": str(run_id)})
    return run


def get(db: Session, run_id: UUID) -> AgentRunOut:
    """Return an agent run's current status, workflow steps, and retry count."""
    return _to_output(get_run_row(db, run_id))


def create_run(db: Session, req: AgentRequestIn, actor: str) -> AgentRun:
    """Persist and enqueue a PENDING graph run; the request transaction owns commit."""
    actor_id = actor.strip()
    if not actor_id:
        raise RequestValidationFailed("An agent run requires an actor")
    run_id = uuid4()
    state = AgentState(run_id=run_id, request=req, actor=actor_id)
    run = AgentRun(
        id=run_id,
        request=req.model_dump(mode="json"),
        graph_state=state.model_dump(mode="json"),
        checkpoints=[],
        retries=0,
        status=AgentRunStatus.PENDING.value,
        explanation={},
    )
    db.add(run)
    db.flush()
    audit_record(
        db,
        "agent_run",
        run.id,
        "created",
        None,
        {"status": run.status, "seed": req.seed},
        actor_id,
    )
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    _EXECUTOR.submit(_execute, run.id, factory)
    return run


def start(db: Session, req: AgentRequestIn, actor: str) -> AgentRunOut:
    """Create a graph run and return its initial pollable response immediately."""
    return _to_output(create_run(db, req, actor))


def persist_state(
    db: Session,
    state: AgentState,
    *,
    status: AgentRunStatus | None = None,
) -> AgentRun:
    """Persist a node checkpoint without committing the caller-owned workflow transaction."""
    run = get_run_row(db, state.run_id)
    previous_status = run.status
    run.graph_state = state.model_dump(mode="json")
    run.retries = state.retries
    if status is not None:
        run.status = status.value
    if state.explanation is not None:
        run.explanation = state.explanation.model_dump(mode="json")
    checkpoints = list(run.checkpoints)
    seen_steps = {str(item) for item in checkpoints}
    for agent_step in state.steps:
        checkpoint = agent_step.model_dump(mode="json")
        checkpoint_key = str(checkpoint)
        if checkpoint_key not in seen_steps:
            checkpoints.append(checkpoint)
            seen_steps.add(checkpoint_key)
    run.checkpoints = checkpoints
    db.flush()
    if run.status != previous_status:
        audit_record(
            db,
            "agent_run",
            run.id,
            "status_changed",
            {"status": previous_status},
            {"status": run.status, "retries": run.retries},
            state.actor,
        )
    return run


def persist_explanation(db: Session, run: AgentRun, explanation: ExplanationOut) -> None:
    """Persist typed explanation output and an append-only reference audit."""
    run.explanation = explanation.model_dump(mode="json")
    run.graph_state = {
        **run.graph_state,
        "explanation": explanation.model_dump(mode="json"),
    }
    db.flush()
    audit_record(
        db,
        "agent_run",
        run.id,
        "explanation_created",
        None,
        {"evidence_ref_count": len(explanation.evidence_refs)},
        str(run.graph_state.get("actor", "agent")),
    )


def _execute(run_id: UUID, factory: sessionmaker[Session]) -> None:
    """Run a queued workflow with its own session and persist terminal/interrupt state."""
    run_snapshot: dict[str, Any] | None = None
    for _attempt in range(100):
        with factory() as db:
            run = db.get(AgentRun, run_id)
            if run is not None:
                if run.status != AgentRunStatus.PENDING.value:
                    return
                run.status = AgentRunStatus.RUNNING.value
                run_snapshot = dict(run.graph_state)
                run_snapshot["status"] = AgentRunStatus.RUNNING.value
                run.graph_state = run_snapshot
                audit_record(
                    db,
                    "agent_run",
                    run.id,
                    "status_changed",
                    {"status": AgentRunStatus.PENDING.value},
                    {"status": AgentRunStatus.RUNNING.value},
                    str(run.graph_state.get("actor", "agent")),
                )
                db.commit()
                break
        time.sleep(0.05)
    if run_snapshot is None:
        return
    try:
        state = AgentState.model_validate(run_snapshot)
        from backend.app.agents.graph import invoke_graph

        with factory() as db:
            result, interrupted = invoke_graph(db, state)
            status = (
                AgentRunStatus.AWAITING_APPROVAL
                if interrupted
                else result.status
            )
            persist_state(db, result, status=status)
            db.commit()
    except Exception as error:
        with factory() as db:
            run = db.get(AgentRun, run_id)
            if run is None:
                return
            old_status = run.status
            run.status = AgentRunStatus.FAILED.value
            run.graph_state = {**run.graph_state, "error": str(error)[:1000]}
            audit_record(
                db,
                "agent_run",
                run.id,
                "status_changed",
                {"status": old_status},
                {"status": AgentRunStatus.FAILED.value, "error": str(error)[:500]},
                str(run.graph_state.get("actor", "agent")),
            )
            db.commit()


def resume(
    db: Session,
    run_id: UUID,
    approval: ApprovalDecision,
    actor: str | None = None,
) -> AgentRun:
    """Resume an interrupted agent graph with a typed human approval decision."""
    run = get_run_row(db, run_id)
    if run.status != AgentRunStatus.AWAITING_APPROVAL.value:
        raise ConflictError("Agent run is not waiting for human approval", {"status": run.status})
    state = AgentState.model_validate(run.graph_state)
    choice = ApprovalDecision(approval)
    if choice == ApprovalDecision.APPROVED and state.verification != "verified":
        raise ConflictError(
            "Only an independently VERIFIED agent result can be approved",
            {"verification": state.verification.value if state.verification else None},
        )
    reviewer = actor.strip() if actor and actor.strip() else state.actor
    from backend.app.agents.graph import invoke_graph

    result, interrupted = invoke_graph(
        db,
        state,
        resume={"decision": choice.value, "actor": reviewer},
    )
    if interrupted:
        raise ConflictError("Agent workflow remains interrupted after the approval response")
    persist_state(db, result, status=result.status)
    audit_record(
        db,
        "agent_run",
        run.id,
        "human_resumed",
        {"status": AgentRunStatus.AWAITING_APPROVAL.value},
        {"status": result.status.value, "decision": choice.value},
        reviewer,
    )
    db.flush()
    return run
