"""Lightweight ARIMA(1,1,0) baseline with residual prediction intervals."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
import pandas as pd  # type: ignore[import-untyped]


@dataclass(frozen=True)
class ForecastResult:
    """Forecast means and lower/upper prediction bounds."""

    mean: np.ndarray
    lower: np.ndarray
    upper: np.ndarray


def fit_predict(
    train: pd.DataFrame,
    test: pd.DataFrame,
    seed: int,
) -> ForecastResult:
    """Fit an AR(1) process on first differences and predict requested feature rows.

    Args:
        train: Past-only frame containing a numeric ``target`` column.
        test: Past-only lagged feature rows to forecast.
        seed: Accepted for interface reproducibility; this implementation is deterministic.

    Returns:
        Mean forecasts and empirically estimated Gaussian residual intervals.

    Raises:
        ValueError: If input data are empty, malformed, or non-finite.
    """
    del seed
    if "target" not in train or train.empty or test.empty:
        raise ValueError("ARIMA requires non-empty train target and test feature rows")
    values = pd.to_numeric(train["target"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("ARIMA training observations must be finite")
    differences = np.diff(values)
    intercept = 0.0
    autoregressive = 0.0
    innovation_scale = 0.0
    if differences.size == 1:
        intercept = float(differences[0])
    elif differences.size >= 2:
        design = np.column_stack((np.ones(differences.size - 1), differences[:-1]))
        coefficients, _, _, _ = np.linalg.lstsq(design, differences[1:], rcond=None)
        intercept = float(coefficients[0])
        autoregressive = float(np.clip(coefficients[1], -0.99, 0.99))
        residuals = differences[1:] - design @ coefficients
        innovation_scale = float(np.sqrt(np.mean(residuals**2)))

    lag_one = next((name for name in test.columns if name.endswith("_lag_1")), None)
    if lag_one is None:
        raise ValueError("ARIMA test features must include a lag-1 column")
    lag_two = next((name for name in test.columns if name.endswith("_lag_2")), None)
    latest = test[lag_one].fillna(0.0).to_numpy(dtype=float)
    previous = test[lag_two].fillna(0.0).to_numpy(dtype=float) if lag_two is not None else latest
    if not np.isfinite(latest).all() or not np.isfinite(previous).all():
        raise ValueError("ARIMA lag inputs must be finite")
    predicted_difference = intercept + autoregressive * (latest - previous)
    mean = latest + predicted_difference
    horizon_steps = (
        test["forecast_horizon_step"].to_numpy(dtype=float)
        if "forecast_horizon_step" in test
        else np.ones(len(test), dtype=float)
    )
    scale = innovation_scale * np.sqrt(np.maximum(horizon_steps, 1.0))
    quantile = NormalDist().inv_cdf(0.975)
    return ForecastResult(
        mean=mean,
        lower=mean - quantile * scale,
        upper=mean + quantile * scale,
    )
