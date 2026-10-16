"""Shared state-step update helpers for deterministic service nodes."""

from __future__ import annotations

from typing import Any

from backend.app.agents.state import AgentState
from backend.app.schemas.agents import AgentStep


def step(state: AgentState, name: str, status: str, **details: Any) -> list[AgentStep]:
    """Append one typed, JSON-safe node checkpoint to the workflow state."""
    return [
        *state.steps,
        AgentStep(name=name, status=status, details=details),
    ]
