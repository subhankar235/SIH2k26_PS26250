"""Read-only benchmark result routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.deps import Actor, get_db, require_role
from backend.app.schemas.benchmarks import AblationOut, BenchmarkResultOut
from backend.app.services.api_dispatch import dispatch

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])
VIEWER = require_role("viewer", "analyst", "approver", "admin")


@router.get("/results", response_model=list[BenchmarkResultOut])
def results(
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(VIEWER)],
    scenario: str | None = None,
    seed: int | None = None,
) -> list[BenchmarkResultOut]:
    """List benchmark results with optional scenario and seed filters.

    Args:
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.
        scenario: Optional synthetic scenario filter.
        seed: Optional deterministic seed filter.

    Returns:
        Benchmark results matching the filters.

    Raises:
        AirPowerError: If authorization or the benchmark service rejects the request.
    """
    filters = {
        key: value
        for key, value in {"scenario": scenario, "seed": seed}.items()
        if value is not None
    }
    return dispatch("backend.app.services.benchmarking.results_service", "results", db, filters)


@router.get("/ablations", response_model=list[AblationOut])
def ablations(
    db: Annotated[Session, Depends(get_db)],
    _actor: Annotated[Actor, Depends(VIEWER)],
) -> list[AblationOut]:
    """List comparative ablation outcomes.

    Args:
        db: Request-scoped database session.
        _actor: Authenticated viewer-or-higher actor.

    Returns:
        Ablation results and their baseline comparisons.

    Raises:
        AirPowerError: If authorization or the benchmark service rejects the request.
    """
    return dispatch("backend.app.services.benchmarking.results_service", "ablations", db)
