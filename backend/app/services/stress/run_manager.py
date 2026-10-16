"""Persist, enqueue, execute, and retrieve synthetic stress runs."""

from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.app.core.exceptions import NotFoundError, RequestValidationFailed
from backend.app.db.models.experiment import ExperimentRun
from backend.app.schemas.stress import StressRunIn
from backend.app.services.audit.audit_service import record as audit_record
from simulation.runner import metrics as stress_metrics
from simulation.runner import mlflow_logger, run_scenario

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="stress-run")


def _session_factory() -> Any:
    """Resolve the configured session factory lazily for worker isolation."""
    from backend.app.db.session import SessionLocal

    return SessionLocal


def start_run(
    db: Session,
    req: StressRunIn,
    actor: str,
    background_tasks: BackgroundTasks | None = None,
) -> ExperimentRun:
    """Persist and enqueue a reproducible stress run without executing it inline.

    Args:
        db: Request-scoped synchronous database session.
        req: Scenario name, random seed, and fault severity.
        actor: Authenticated user launching the experiment.
        background_tasks: FastAPI response task queue; an executor is used for direct
            service invocations that do not have a request queue.

    Returns:
        The flushed run in ``queued`` status.

    Raises:
        RequestValidationFailed: If actor or scenario parameters are invalid.
        SQLAlchemyError: If the run or audit record cannot be persisted.
    """
    scenario = req.scenario.strip()
    actor_id = actor.strip()
    if not actor_id:
        raise RequestValidationFailed("A stress run requires an actor")
    if not scenario or len(scenario) > 255:
        raise RequestValidationFailed("Scenario must contain 1 to 255 characters")
    if req.seed < 0:
        raise RequestValidationFailed("Stress-run seed must be non-negative")
    if not math.isfinite(req.severity) or not 0 <= req.severity <= 1:
        raise RequestValidationFailed("Stress-run severity must be finite and within [0, 1]")

    config = {
        "severity": float(req.severity),
        "actor": actor_id,
    }
    run = ExperimentRun(
        scenario=scenario,
        seed=req.seed,
        status="queued",
        config=config,
        metrics={},
    )
    db.add(run)
    db.flush()
    audit_record(
        db,
        "experiment_run",
        run.id,
        "queued",
        None,
        {"scenario": run.scenario, "seed": run.seed, "status": run.status},
        actor_id,
    )
    if background_tasks is not None:
        background_tasks.add_task(execute_run, run.id)
    else:
        _EXECUTOR.submit(execute_run, run.id)
    return run


def get_run(db: Session, run_id: UUID) -> ExperimentRun:
    """Return a persisted stress run for API polling.

    Args:
        db: Active synchronous database session.
        run_id: UUID of the requested experiment.

    Returns:
        Current run status, configuration, and metrics.

    Raises:
        NotFoundError: If the run does not exist.
    """
    run = db.get(ExperimentRun, run_id)
    if run is None:
        raise NotFoundError("Stress run not found", {"id": str(run_id)})
    return run


def execute_run(run_id: UUID) -> None:
    """Execute one queued scenario in an isolated DB session and persist its outcome.

    Args:
        run_id: Experiment UUID enqueued by :func:`start_run`.

    Returns:
        None. Results and terminal status are persisted for ``get_run`` polling.
    """
    factory = _session_factory()
    run_snapshot: dict[str, Any] | None = None
    for _attempt in range(20):
        with factory() as db:
            run = db.get(ExperimentRun, run_id)
            if run is not None:
                if run.status in {"running", "completed", "failed"}:
                    return
                actor = str(run.config.get("actor", "stress-worker"))
                run_snapshot = {
                    "scenario": run.scenario,
                    "seed": run.seed,
                    "severity": float(run.config.get("severity", 0.5)),
                    "actor": actor,
                }
                _set_running = run.status
                claimed = db.execute(
                    update(ExperimentRun)
                    .where(ExperimentRun.id == run.id, ExperimentRun.status == "queued")
                    .values(status="running")
                    .execution_options(synchronize_session=False)
                )
                if claimed.rowcount != 1:
                    db.rollback()
                    return
                audit_record(
                    db,
                    "experiment_run",
                    run.id,
                    "status_changed",
                    {"status": _set_running},
                    {"status": "running"},
                    actor,
                )
                db.commit()
                break
        # A web request's transaction may commit just after its background callback starts.
        time.sleep(0.025)
    if run_snapshot is None:
        return

    try:
        scenario = run_scenario.Scenario(
            name=run_snapshot["scenario"],
            severity=run_snapshot["severity"],
        )
        result = run_scenario.run(scenario, run_snapshot["seed"])
        metrics = stress_metrics.compute(result, result.labels)
        try:
            mlflow_run_id = mlflow_logger.log_run(
                result,
                metrics,
                seed=run_snapshot["seed"],
                scenario=run_snapshot["scenario"],
            )
        except Exception as error:  # MLflow is optional and must not discard simulation results.
            mlflow_run_id = ""
            metrics["mlflow_error"] = str(error)[:500]
        with factory() as db:
            run = db.get(ExperimentRun, run_id)
            if run is None or run.status != "running":
                return
            run.metrics = metrics
            run.mlflow_run_id = mlflow_run_id or None
            old_status = run.status
            run.status = "failed" if result.failed else "completed"
            audit_record(
                db,
                "experiment_run",
                run.id,
                "status_changed",
                {"status": old_status},
                {
                    "status": run.status,
                    "metric_names": sorted(metrics),
                    "mlflow_run_id": run.mlflow_run_id,
                },
                run_snapshot["actor"],
            )
            db.commit()
    except Exception as error:
        with factory() as db:
            run = db.get(ExperimentRun, run_id)
            if run is None or run.status != "running":
                return
            old_status = run.status
            run.status = "failed"
            run.metrics = {"error": str(error)[:1000]}
            audit_record(
                db,
                "experiment_run",
                run.id,
                "status_changed",
                {"status": old_status},
                {"status": "failed", "error": str(error)[:500]},
                run_snapshot["actor"],
            )
            db.commit()
