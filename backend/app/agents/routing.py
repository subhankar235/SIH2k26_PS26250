"""Deterministic conditional routing after authoritative verification."""

from __future__ import annotations

from typing import Literal

from backend.app.agents.retry import changed_since_last
from backend.app.agents.state import AgentState
from backend.app.core.enums import VerificationOutcome


def route_after_verify(state: AgentState) -> Literal["reanalyse", "explain", "escalate"]:
    """Route solely from the verifier result and bounded retry/change state."""
    if state.verification == VerificationOutcome.VERIFIED:
        return "explain"
    if state.verification not in {VerificationOutcome.INVALID, VerificationOutcome.UNCERTAIN}:
        return "escalate"
    from backend.app.core.config import get_settings

    maximum = get_settings().max_agent_retries
    if state.retries >= maximum:
        return "escalate"
    if state.last_attempt_fingerprint is not None and not changed_since_last(
        state, state.last_attempt_fingerprint
    ):
        return "escalate"
    return "reanalyse"
