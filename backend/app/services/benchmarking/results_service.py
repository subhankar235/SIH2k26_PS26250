"""Read persisted experiment metrics and summarize baseline/ablation comparisons."""

from __future__ import annotations

import math
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models.experiment import ExperimentRun
from backend.app.schemas.benchmarks import AblationOut, BenchmarkResultOut


def _numeric_metrics(value: object) -> dict[str, float]:
    """Select finite scalar numeric metrics for the public result contract."""
    if not isinstance(value, dict):
        return {}
    result: dict[str, float] = {}
    for name, raw in value.items():
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            continue
        numeric = float(raw)
        if math.isfinite(numeric):
            result[str(name)] = numeric
    return result


def _mlflow_data(run_id: str | None) -> tuple[dict[str, float], dict[str, Any]]:
    """Read optional MLflow metric/parameter metadata without making it mandatory."""
    if not run_id:
        return {}, {}
    try:
        from mlflow import MlflowClient  # type: ignore[import-not-found]

        run = MlflowClient(tracking_uri=get_settings().mlflow_tracking_uri).get_run(run_id)
        metrics = _numeric_metrics(run.data.metrics)
        metadata = {str(key): value for key, value in run.data.params.items()}
        return metrics, metadata
    except Exception:
        # The persisted experiment row remains authoritative when MLflow is unavailable.
        return {}, {}


def _experiment_filters(filters: dict[str, Any]) -> list[Any]:
    """Convert supported public filters to SQL predicates."""
    predicates: list[Any] = []
    scenario = filters.get("scenario")
    if scenario is not None:
        if not isinstance(scenario, str) or not scenario.strip():
            raise ValueError("scenario filter must be a non-empty string")
        predicates.append(ExperimentRun.scenario == scenario.strip())
    seed = filters.get("seed")
    if seed is not None:
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
            raise ValueError("seed filter must be a non-negative integer")
        predicates.append(ExperimentRun.seed == seed)
    experiment_id = filters.get("experiment_id")
    if experiment_id is not None:
        predicates.append(ExperimentRun.id == UUID(str(experiment_id)))
    return predicates


def results(db: Session, filters: dict[str, Any]) -> list[BenchmarkResultOut]:
    """Read completed experiment rows and enrich them with optional MLflow metadata.

    Args:
        db: Active synchronous database session.
        filters: Supported keys are ``scenario``, ``seed``, and ``experiment_id``.

    Returns:
        Stable ordered benchmark results with scalar finite metrics.
    """
    predicates = _experiment_filters(filters)
    statement = select(ExperimentRun).where(ExperimentRun.status == "completed")
    if predicates:
        statement = statement.where(*predicates)
    rows = list(
        db.scalars(statement.order_by(ExperimentRun.created_at.desc(), ExperimentRun.id)).all()
    )
    result: list[BenchmarkResultOut] = []
    for row in rows:
        mlflow_metrics, mlflow_params = _mlflow_data(row.mlflow_run_id)
        metrics = {**_numeric_metrics(row.metrics), **mlflow_metrics}
        raw_experiment_id = row.config.get("experiment_id", row.id)
        try:
            experiment_id = UUID(str(raw_experiment_id))
        except (TypeError, ValueError):
            experiment_id = row.id
        result.append(
            BenchmarkResultOut(
                id=row.id,
                experiment_id=experiment_id,
                scenario=row.scenario,
                seed=row.seed,
                metrics=metrics,
                metadata={
                    "status": row.status,
                    "config": row.config,
                    "mlflow_run_id": row.mlflow_run_id,
                    "mlflow_params": mlflow_params,
                },
            )
        )
    return result


def _comparison(
    name: str,
    baseline: object,
    ablation: object,
) -> AblationOut | None:
    """Build one finite scalar metric comparison and subtract baseline from ablation."""
    baseline_metrics = _numeric_metrics(baseline)
    ablation_metrics = _numeric_metrics(ablation)
    shared = sorted(baseline_metrics.keys() & ablation_metrics.keys())
    if not shared:
        return None
    baseline_metrics = {key: baseline_metrics[key] for key in shared}
    ablation_metrics = {key: ablation_metrics[key] for key in shared}
    return AblationOut(
        name=name,
        baseline_metrics=baseline_metrics,
        ablation_metrics=ablation_metrics,
        delta={key: ablation_metrics[key] - baseline_metrics[key] for key in shared},
    )


def ablations(db: Session) -> list[AblationOut]:
    """Summarize configured ablations and persisted no-detection baselines.

    An experiment can opt into an explicitly named ablation with
    ``config.ablation_name``, ``config.baseline_metrics``, and either
    ``config.ablation_metrics`` or its run metrics. Stress runs automatically expose
    their persisted ``baselines.no_detection`` comparison when available.
    """
    rows = list(
        db.scalars(
            select(ExperimentRun)
            .where(ExperimentRun.status == "completed")
            .order_by(ExperimentRun.scenario, ExperimentRun.seed, ExperimentRun.id)
        ).all()
    )
    comparisons: list[AblationOut] = []
    for row in rows:
        config = row.config if isinstance(row.config, dict) else {}
        if config.get("ablation_name"):
            comparison = _comparison(
                str(config["ablation_name"]),
                config.get("baseline_metrics"),
                config.get("ablation_metrics", row.metrics),
            )
            if comparison is not None:
                comparisons.append(comparison)
        metrics = row.metrics if isinstance(row.metrics, dict) else {}
        baselines = metrics.get("baselines", {})
        if isinstance(baselines, dict):
            for baseline_name, baseline_metrics in sorted(baselines.items()):
                comparison = _comparison(
                    f"{row.scenario}:{baseline_name}",
                    baseline_metrics,
                    metrics,
                )
                if comparison is not None:
                    comparisons.append(comparison)
    return comparisons
