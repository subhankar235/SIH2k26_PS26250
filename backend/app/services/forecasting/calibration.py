"""Calibration metrics for probabilistic forecasts."""

from __future__ import annotations

import numpy as np

from backend.app.db.models.forecast import Forecast


def _aligned_arrays(
    y: np.ndarray,
    *arrays: np.ndarray,
) -> tuple[np.ndarray, ...]:
    """Convert metric inputs to aligned finite one-dimensional float arrays."""
    converted = tuple(np.asarray(values, dtype=float) for values in (y, *arrays))
    if (
        converted[0].ndim != 1
        or not converted[0].size
        or any(values.shape != converted[0].shape for values in converted[1:])
    ):
        raise ValueError("metric inputs must be one-dimensional arrays of the same non-zero shape")
    if any(not np.isfinite(values).all() for values in converted):
        raise ValueError("metric inputs must be finite")
    return converted


def coverage(y: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    """Compute empirical coverage of forecast prediction intervals.

    Args:
        y: Observed values.
        lower: Prediction interval lower bounds.
        upper: Prediction interval upper bounds.

    Returns:
        Fraction of observations contained within their intervals.

    Raises:
        ValueError: If arrays do not align, are empty, non-finite, or contain invalid intervals.
    """
    actual, low, high = _aligned_arrays(y, lower, upper)
    if np.any(low > high):
        raise ValueError("lower bounds must not exceed upper bounds")
    return float(np.mean((actual >= low) & (actual <= high)))


def ece(y: np.ndarray, mean: np.ndarray, std: np.ndarray, bins: int = 10) -> float:
    """Compute regression expected calibration error over uncertainty bins.

    Args:
        y: Observed values.
        mean: Forecast means.
        std: Predicted standard deviations.
        bins: Maximum number of equal-count uncertainty groups.

    Returns:
        Weighted absolute difference between empirical RMSE and predicted RMS scale.

    Raises:
        ValueError: If arrays are empty, non-finite, misaligned, or scales/bins are invalid.
    """
    actual, predicted, deviations = _aligned_arrays(y, mean, std)
    if bins < 1 or np.any(deviations < 0):
        raise ValueError("bins must be positive and standard deviations non-negative")
    order = np.argsort(deviations, kind="stable")
    groups = np.array_split(order, min(bins, len(order)))
    error = 0.0
    for indices in groups:
        rmse = float(np.sqrt(np.mean((actual[indices] - predicted[indices]) ** 2)))
        predicted_scale = float(np.sqrt(np.mean(deviations[indices] ** 2)))
        error += (len(indices) / len(order)) * abs(rmse - predicted_scale)
    return float(error)


def nll(y: np.ndarray, mean: np.ndarray, std: np.ndarray) -> float:
    """Compute average Gaussian negative log likelihood.

    Args:
        y: Observed values.
        mean: Forecast means.
        std: Predicted standard deviations.

    Returns:
        Average negative log likelihood in nats per observation.

    Raises:
        ValueError: If arrays are empty/non-finite/misaligned or standard deviations are negative.
    """
    actual, predicted, deviations = _aligned_arrays(y, mean, std)
    if np.any(deviations < 0):
        raise ValueError("standard deviations must be non-negative")
    safe_std = np.maximum(deviations, 1e-12)
    losses = 0.5 * np.log(2.0 * np.pi * safe_std**2) + 0.5 * ((actual - predicted) / safe_std) ** 2
    return float(np.mean(losses))


def flag_high_uncertainty(forecast: Forecast, threshold: float) -> bool:
    """Flag forecasts whose relative interval width exceeds a threshold.

    Args:
        forecast: Persisted forecast containing mean/lower/upper points.
        threshold: Maximum acceptable relative interval width.

    Returns:
        True when any forecast point exceeds the threshold.

    Raises:
        ValueError: If threshold is negative or point values are malformed.
    """
    if not np.isfinite(threshold) or threshold < 0:
        raise ValueError("uncertainty threshold must be finite and non-negative")
    for point in forecast.points:
        mean = float(point["mean"])
        lower = float(point["lower"])
        upper = float(point["upper"])
        if lower > upper:
            raise ValueError("forecast lower bound must not exceed upper bound")
        relative_width = (upper - lower) / max(abs(mean), 1e-8)
        if relative_width > threshold:
            return True
    return False
