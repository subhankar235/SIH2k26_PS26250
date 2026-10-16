"""Bounded agent retry accounting and deterministic change fingerprints."""

from __future__ import annotations

import hashlib
import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from backend.app.agents.state import AgentState
from backend.app.core.enums import AgentRunStatus

T = TypeVar("T", bound=BaseModel)


def fingerprint(state: AgentState) -> str:
    """Hash the request and observed evidence/forecast/change inputs canonically."""
    payload = {
        "request": state.request.model_dump(mode="json"),
        "evidence": state.evidence.model_dump(mode="json") if state.evidence else None,
        "forecast_ids": sorted(str(item) for item in state.forecast_ids),
        "changes": [item.model_dump(mode="json") for item in state.changes],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def next_attempt(state: AgentState, max_retries: int) -> AgentState:
    """Increment retries once or mark the state escalated when its budget is exhausted."""
    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    if state.retries >= max_retries:
        return state.model_copy(update={"status": AgentRunStatus.ESCALATED})
    return state.model_copy(
        update={
            "retries": state.retries + 1,
            "last_attempt_fingerprint": fingerprint(state),
        }
    )


def changed_since_last(state: AgentState, prev_fingerprint: str) -> bool:
    """Return whether inputs changed since a prior attempt fingerprint."""
    if not prev_fingerprint:
        return True
    return fingerprint(state) != prev_fingerprint


def parse_output_with_retry(
    producer: Any,
    output_type: type[T],
) -> T:
    """Validate an agent/LLM output as Pydantic, retrying one schema failure once.

    ``producer`` may be a parsed object or a callable producing a raw JSON value.
    The callable is invoked at most twice; a second failure is surfaced to the
    workflow, whose outer bounded retry policy can escalate it.
    """
    attempts = 2 if callable(producer) else 1
    last_error: ValidationError | None = None
    for _ in range(attempts):
        raw = producer() if callable(producer) else producer
        try:
            return output_type.model_validate(raw)
        except ValidationError as error:
            last_error = error
    assert last_error is not None
    raise last_error
