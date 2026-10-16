"""Shared autoregressive training data and input validation for baselines."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ForecastResult:
    """Forecast means and lower/upper prediction bounds."""

    mean: np.ndarray
    lower: np.ndarray
    upper: np.ndarray


def target_values(train: pd.DataFrame, test: pd.DataFrame) -> tuple[np.ndarray, int]:
    """Validate target histories and return target observations and forecast length."""
    if not isinstance(train, pd.DataFrame) or not isinstance(test, pd.DataFrame):
        raise ValueError("train and test must be pandas DataFrames")
    if "target" not in train or train.empty:
        raise ValueError("training data must contain a non-empty target column")
    if test.empty:
        raise ValueError("test feature frame must not be empty")
    values = pd.to_numeric(train["target"], errors="coerce").to_numpy(dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("training targets must be finite numeric values")
    return values, len(test)


def supervised_windows(values: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    """Create chronological sliding-window inputs with next-value labels."""
    if window < 1 or len(values) <= window:
        raise ValueError("training history must contain more points than the lag window")
    x = np.stack([values[index - window : index] for index in range(window, len(values))])
    y = values[window:]
    return x.astype(np.float32), y.astype(np.float32)


def recursive_forecast(values: np.ndarray, forecast_fn, horizon: int) -> np.ndarray:
    """Forecast one step at a time, feeding each prediction into later horizons."""
    history = np.asarray(values, dtype=np.float64).tolist()
    predictions: list[float] = []
    for _ in range(horizon):
        prediction = float(forecast_fn(np.asarray(history, dtype=np.float32)))
        if not np.isfinite(prediction):
            raise FloatingPointError("baseline produced a non-finite forecast")
        history.append(prediction)
        predictions.append(prediction)
    return np.asarray(predictions, dtype=np.float64)


def residual_scale(values: np.ndarray, window: int, predictor) -> float:
    """Estimate one-step residual scale on the training history without future leakage."""
    if len(values) <= window + 1:
        return float(np.std(np.diff(values))) if len(values) > 1 else 0.0
    errors = []
    for index in range(window, len(values)):
        prediction = float(predictor(values[:index]))
        errors.append(float(values[index] - prediction))
    return float(np.sqrt(np.mean(np.square(errors)))) if errors else 0.0
