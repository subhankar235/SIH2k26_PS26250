"""Changed-input analysis node backed by F6/F3 services."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.app.agents.nodes.common import step
from backend.app.agents.state import AgentState, current_session
from backend.app.schemas.validity import ChangeEvent, InputRef
from backend.app.services.replanning.diff_inputs import diff_inputs
from backend.app.services.validity.reverifier import reverify


def _input_refs(value: object) -> dict[str, InputRef]:
    """Parse a request mapping of input references through the API schema."""
    if not isinstance(value, dict):
        return {}
    refs: dict[str, InputRef] = {}
    for key, item in value.items():
        refs[str(key)] = InputRef.model_validate(item)
    return refs


def run(state: AgentState, db: Session | None = None) -> AgentState:
    """Diff explicit input snapshots and reverifiy dependent decisions when requested."""
    request: dict[str, Any] = state.request.request
    changes = [ChangeEvent.model_validate(item) for item in request.get("changes", [])]
    if request.get("old_inputs") is not None or request.get("new_inputs") is not None:
        changes.extend(
            diff_inputs(
                _input_refs(request.get("old_inputs", {})),
                _input_refs(request.get("new_inputs", {})),
            )
        )
    unique = {
        (change.input_type, change.input_id): change
        for change in changes
    }
    normalized = sorted(unique.values(), key=lambda item: (item.input_type, str(item.input_id)))
    details: dict[str, Any] = {"change_count": len(normalized)}
    if normalized:
        outcome = reverify(current_session(db), normalized)
        details.update(
            affected_decisions=len(outcome.affected),
            nodes_touched=outcome.nodes_touched,
        )
    return state.model_copy(
        update={
            "changes": normalized,
            "steps": step(
                state,
                "change_analysis",
                "completed" if normalized else "skipped",
                **details,
            ),
        }
    )
