"""Leakage-safe time-series feature construction."""

from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]


def build_features(
    df: pd.DataFrame,
    target: str,
    lags: list[int],
    windows: list[int],
) -> pd.DataFrame:
    """Build lagged, trailing-window, and optional known calendar/weather features.

    Args:
        df: Chronologically indexed frame containing the target history.
        target: Name of the numeric target column.
        lags: Positive observation lags to include.
        windows: Positive trailing-window widths to summarize.

    Returns:
        Feature frame containing only prior target values and known exogenous values.
        Lag warm-up rows retain NaNs; callers must trim them before model fitting rather
        than imputing them from future observations.

    Raises:
        ValueError: If target, lags, windows, or target values are invalid.
    """
    if df.empty:
        raise ValueError("feature input must not be empty")
    if not df.columns.is_unique:
        raise ValueError("feature input must not have duplicate columns")
    if target not in df.columns:
        raise ValueError(f"target column {target!r} is missing")
    if any(lag < 1 for lag in lags) or any(window < 1 for window in windows):
        raise ValueError("lags and windows must contain positive integers")
    if isinstance(df.index, pd.DatetimeIndex) and not df.index.is_monotonic_increasing:
        raise ValueError("datetime index must be in chronological order")
    ordered = df.copy()
    values = pd.to_numeric(ordered[target], errors="coerce")
    if values.isna().any() or not np.isfinite(values.to_numpy(dtype=float)).all():
        raise ValueError("target values must be finite numeric values")

    features = pd.DataFrame(index=ordered.index)
    for lag in sorted(set(lags)):
        features[f"{target}_lag_{lag}"] = values.shift(lag)
    prior = values.shift(1)
    for window in sorted(set(windows)):
        rolling = prior.rolling(window=window, min_periods=1)
        features[f"{target}_rolling_mean_{window}"] = rolling.mean()
        features[f"{target}_rolling_std_{window}"] = rolling.std(ddof=0).fillna(0.0)

    if isinstance(ordered.index, pd.DatetimeIndex):
        hour = ordered.index.hour.to_numpy(dtype=float)
        day_of_week = ordered.index.dayofweek.to_numpy(dtype=float)
        features["calendar_hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
        features["calendar_hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
        features["calendar_weekday_sin"] = np.sin(2 * np.pi * day_of_week / 7.0)
        features["calendar_weekday_cos"] = np.cos(2 * np.pi * day_of_week / 7.0)

    for column in ("temperature_c", "wind_speed_mps", "precipitation_mm"):
        if column in ordered.columns and column != target:
            weather = pd.to_numeric(ordered[column], errors="coerce")
            if weather.isna().any() or not np.isfinite(weather.to_numpy(dtype=float)).all():
                raise ValueError(f"weather feature {column!r} must contain finite values")
            features[f"{column}_lag_1"] = weather.shift(1)
    return features
