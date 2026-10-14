"""Planning-input validation and solver-neutral problem construction."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.app.schemas.planning import ProblemIn
from backend.app.services.optimization.integration.input_adapter import to_problem
from backend.app.services.optimization.models.problem import Problem


def build_problem(db: Session | None, request: ProblemIn | dict[str, Any]) -> Problem:
    """Build a problem from the explicit planning request snapshot.

    The current request is the authoritative task and resource snapshot; generic
    normalized records do not define task scheduling fields.
    """
    _ = db
    payload = request.model_dump(mode="python") if isinstance(request, ProblemIn) else request
    return to_problem(payload)
