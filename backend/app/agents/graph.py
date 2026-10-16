"""LangGraph orchestration with bounded retries and verifier-controlled routing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.agents import checkpointing
from backend.app.agents.human_approval import approval_interrupt
from backend.app.agents.nodes import (
    change_analysis_agent,
    evidence_agent,
    explanation_agent,
    optimisation_node,
    prediction_agent,
    verification_node,
)
from backend.app.agents.retry import next_attempt
from backend.app.agents.routing import route_after_verify
from backend.app.agents.state import AgentState, bind_session
from backend.app.core.config import get_settings
from backend.app.core.enums import AgentRunStatus, ApprovalDecision
from backend.app.schemas.agents import AgentRequestIn


def _node(function: Callable[[AgentState], AgentState]) -> Any:
    """Adapt a typed AgentState node to LangGraph's dict state-update interface."""
    def invoke(value: Any) -> dict[str, Any]:
        state = value if isinstance(value, AgentState) else AgentState.model_validate(value)
        return function(state).model_dump(mode="python")

    return invoke


def _retry_node(value: Any) -> dict[str, Any]:
    """Record one bounded verification retry before re-analysis begins."""
    state = value if isinstance(value, AgentState) else AgentState.model_validate(value)
    retried = next_attempt(state, get_settings().max_agent_retries)
    return retried.model_dump(mode="python")


def _escalate_node(value: Any) -> dict[str, Any]:
    """Mark exhausted or unchanged-invalid workflows for human review."""
    state = value if isinstance(value, AgentState) else AgentState.model_validate(value)
    from backend.app.agents.nodes.common import step

    return state.model_copy(
        update={
            "status": AgentRunStatus.ESCALATED,
            "steps": step(
                state,
                "escalate",
                "completed",
                retries=state.retries,
                verification=state.verification.value if state.verification else None,
            ),
        }
    ).model_dump(mode="python")


def build_graph(
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph[AgentState, AgentState, AgentState]:
    """Build the checkpointed evidence-to-approval LangGraph.

    Args:
        checkpointer: Persistent saver for PostgreSQL or in-memory test saver.

    Returns:
        Compiled graph with state transitions checkpointed by ``run_id`` thread id.
    """
    builder = StateGraph(AgentState)
    builder.add_node("evidence", cast(Any, _node(evidence_agent.run)))
    builder.add_node("prediction", cast(Any, _node(prediction_agent.run)))
    builder.add_node("change_analysis", cast(Any, _node(change_analysis_agent.run)))
    builder.add_node("optimise", cast(Any, _node(optimisation_node.run)))
    builder.add_node("verify", cast(Any, _node(verification_node.run)))
    builder.add_node("retry", cast(Any, _retry_node))
    builder.add_node("escalate", cast(Any, _escalate_node))
    builder.add_node("explain", cast(Any, _node(explanation_agent.run)))
    builder.add_node("human_approval", cast(Any, _node(approval_interrupt)))

    builder.add_edge(START, "evidence")
    builder.add_edge("evidence", "prediction")
    builder.add_edge("prediction", "change_analysis")
    builder.add_edge("change_analysis", "optimise")
    builder.add_edge("optimise", "verify")
    builder.add_conditional_edges(
        "verify",
        route_after_verify,
        {"reanalyse": "retry", "explain": "explain", "escalate": "escalate"},
    )
    builder.add_edge("retry", "evidence")
    builder.add_edge("escalate", "human_approval")
    builder.add_edge("explain", "human_approval")
    builder.add_edge("human_approval", END)
    return builder.compile(checkpointer=checkpointer)


def invoke_graph(
    db: Session,
    state: AgentState,
    *,
    resume: object | None = None,
) -> tuple[AgentState, bool]:
    """Invoke or resume one graph thread with its DB session bound to service nodes."""
    bind = db.get_bind()
    database_url = str(bind.url) if isinstance(bind, Engine) else str(bind.engine.url)
    config: RunnableConfig = {"configurable": {"thread_id": str(state.run_id)}}
    with checkpointing.get_checkpointer(database_url) as saver:
        compiled = build_graph(saver)
        with bind_session(db):
            if resume is None:
                output = compiled.invoke(state, config=config)
            else:
                output = compiled.invoke(Command(resume=resume), config=config)
    if not isinstance(output, dict):
        raise TypeError("LangGraph returned a non-object workflow state")
    interrupted = bool(output.get("__interrupt__"))
    fields = AgentState.model_fields
    payload = {key: value for key, value in output.items() if key in fields}
    return AgentState.model_validate(payload), interrupted


def start(db: Session, req: AgentRequestIn, actor: str) -> Any:
    """Create and enqueue a new agent run through the service-owned persistence layer."""
    from backend.app.services.agent_service import create_run

    return create_run(db, req, actor)


def resume(db: Session, run_id: UUID, approval: ApprovalDecision) -> Any:
    """Resume an interrupted graph thread after a typed human decision."""
    from backend.app.services.agent_service import resume

    return resume(db, run_id, approval)
