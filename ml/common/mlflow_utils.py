"""Typed convenience wrappers around MLflow's active-run and logging APIs."""

from __future__ import annotations

import json
import math
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def _mlflow() -> Any:
    """Import MLflow only when tracking is requested."""
    try:
        import mlflow
    except ImportError as error:
        raise RuntimeError(
            "MLflow tracking requires the mlflow package; install ml/requirements.txt"
        ) from error
    return mlflow


def _tracking_value(value: object) -> str:
    """Convert structured params and tags to MLflow's bounded string representation."""
    if isinstance(value, str):
        text = value
    elif value is None or isinstance(value, (int, float, bool)):
        text = str(value)
    else:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return text[:500]


@contextmanager
def start_run(
    experiment: str,
    params: dict[str, Any],
    tags: dict[str, str] | None = None,
) -> Iterator[Any]:
    """Start a named MLflow experiment/run, logging its params and optional tags.

    Usage::

        with start_run("ditto", {"seed": 7}) as run:
            log_metrics({"f1": 0.92})

    Raises:
        ValueError: If experiment, params, or tag keys are malformed.
        RuntimeError: If MLflow is not installed.
        MlflowException: Propagated for tracking server or logging failures.
    """
    name = experiment.strip() if isinstance(experiment, str) else ""
    if not name:
        raise ValueError("experiment must be a non-empty string")
    if not isinstance(params, dict) or any(not isinstance(key, str) or not key for key in params):
        raise ValueError("params must be a mapping with non-empty string keys")
    if tags is not None and (
        not isinstance(tags, dict)
        or any(not isinstance(key, str) or not key for key in tags)
    ):
        raise ValueError("tags must be a mapping with non-empty string keys")

    mlflow = _mlflow()
    selected_experiment = mlflow.set_experiment(name)
    with mlflow.start_run(experiment_id=selected_experiment.experiment_id) as active_run:
        if params:
            mlflow.log_params({key: _tracking_value(value) for key, value in params.items()})
        if tags:
            mlflow.set_tags({key: _tracking_value(value) for key, value in tags.items()})
        yield active_run


def log_metrics(metrics: dict[str, float], step: int | None = None) -> None:
    """Log finite numeric metrics to the active run, optionally at one step."""
    if not isinstance(metrics, dict):
        raise TypeError("metrics must be a mapping")
    if step is not None and (not isinstance(step, int) or isinstance(step, bool) or step < 0):
        raise ValueError("step must be a non-negative integer or None")
    cleaned: dict[str, float] = {}
    for key, value in metrics.items():
        if not isinstance(key, str) or not key:
            raise ValueError("metric names must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"metric {key!r} must be numeric")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"metric {key!r} must be finite")
        cleaned[key] = number
    if cleaned:
        _mlflow().log_metrics(cleaned, step=step)


def log_artifact_path(path: Path) -> None:
    """Log a file or directory artifact after validating that it exists."""
    artifact = Path(path)
    if not artifact.exists():
        raise FileNotFoundError(artifact)
    if artifact.is_file():
        _mlflow().log_artifact(str(artifact))
    elif artifact.is_dir():
        _mlflow().log_artifacts(str(artifact))
    else:
        raise ValueError(f"artifact path is neither a regular file nor directory: {artifact}")
