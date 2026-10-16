"""Lightweight ARIMA(1,1,0) baseline with residual prediction intervals."""

from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from ml.forecasting.baselines._common import ForecastResult, target_values


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
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    values, _horizon = target_values(train, test)
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
    latest = pd.to_numeric(test[lag_one], errors="coerce").to_numpy(dtype=float)
    previous = (
        pd.to_numeric(test[lag_two], errors="coerce").to_numpy(dtype=float)
        if lag_two is not None
        else latest
    )
    if not np.isfinite(latest).all() or not np.isfinite(previous).all():
        raise ValueError("ARIMA lag inputs must be finite")
    predicted_difference = intercept + autoregressive * (latest - previous)
    mean = latest + predicted_difference
    horizon_steps = (
        pd.to_numeric(test["forecast_horizon_step"], errors="coerce").to_numpy(dtype=float)
        if "forecast_horizon_step" in test
        else np.ones(len(test), dtype=float)
    )
    if not np.isfinite(horizon_steps).all() or np.any(horizon_steps < 1):
        raise ValueError("forecast_horizon_step must contain finite positive values")
    scale = innovation_scale * np.sqrt(np.maximum(horizon_steps, 1.0))
    quantile = NormalDist().inv_cdf(0.975)
    return ForecastResult(
        mean=mean,
        lower=mean - quantile * scale,
        upper=mean + quantile * scale,
    )
