"""Optional MLflow tracking for completed synthetic stress runs."""

from __future__ import annotations

from typing import Any

from simulation.runner.run_scenario import RunResult


def log_run(
    result: RunResult,
    metrics: dict[str, Any],
    seed: int,
    scenario: str,
) -> str:
    """Log a run to MLflow when the optional client is installed and configured.

    Returns an empty id when MLflow is not installed, allowing offline stress runs.
    """
    try:
        import mlflow  # type: ignore[import-not-found]
    except ImportError:
        return ""

    serializable = {
        key: value
        for key, value in metrics.items()
        if isinstance(value, (int, float)) and key not in {"true_positive", "false_positive"}
    }
    with mlflow.start_run(run_name=scenario) as active_run:
        mlflow.log_params({"scenario": scenario, "seed": seed, "event_count": len(result.events)})
        mlflow.log_metrics({key: float(value) for key, value in serializable.items()})
        return str(active_run.info.run_id)
