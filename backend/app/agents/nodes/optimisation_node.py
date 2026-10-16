"""Deterministic planning or replanning node."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.agents.nodes.common import step
from backend.app.agents.state import AgentState, current_session
from backend.app.schemas.planning import ScheduleOut, SolveIn
from backend.app.schemas.replanning import ReplanIn
from backend.app.services.planning.solver_service import solve_and_verify
from backend.app.services.replanning.incremental_recompute import replan


def _solve_request(request: dict[str, Any], seed: int) -> SolveIn:
    """Normalize either a complete solve request or compact problem request."""
    value = request.get("solve")
    if value is None:
        if "problem" not in request:
            raise ValueError("agent request requires a problem or solve object")
        value = {
            "problem": request["problem"],
            "use_alns": request.get("use_alns", False),
            "time_limit_s": request.get("time_limit_s", 30),
            "seed": request.get("seed", seed),
        }
    if not isinstance(value, dict):
        raise ValueError("agent solve request must be an object")
    if "seed" not in value:
        value = {**value, "seed": seed}
    return SolveIn.model_validate(value)


def run(state: AgentState, db: Session | None = None) -> AgentState:
    """Solve a new schedule or incrementally replan an existing schedule."""
    request = state.request.request
    session = current_session(db)
    parent_id = request.get("schedule_id")
    if parent_id is not None and state.changes:
        replan_request = ReplanIn(
            schedule_id=UUID(str(parent_id)),
            changes=state.changes,
        )
        result = replan(session, replan_request.schedule_id, replan_request.changes, state.actor)
        schedule = result.schedule
        operation = "replanned"
    else:
        solve_request = _solve_request(request, state.request.seed)
        schedule_row = solve_and_verify(session, solve_request, state.actor)
        schedule = ScheduleOut.model_validate(schedule_row)
        operation = "solved"
    return state.model_copy(
        update={
            "schedule_id": schedule.id,
            "steps": step(
                state,
                "optimise",
                "completed",
                operation=operation,
                schedule_id=str(schedule.id),
                schedule_status=str(schedule.status),
            ),
        }
    )
