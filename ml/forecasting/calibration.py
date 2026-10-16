"""Shared calibration metrics for Gaussian and interval forecasts."""

from __future__ import annotations

import numpy as np


def _aligned_arrays(y: np.ndarray, *arrays: np.ndarray) -> tuple[np.ndarray, ...]:
    """Convert metric inputs to aligned finite one-dimensional float arrays."""
    try:
        converted = tuple(np.asarray(values, dtype=float) for values in (y, *arrays))
    except (TypeError, ValueError) as error:
        raise ValueError("metric inputs must be numeric arrays") from error
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
    """Compute the fraction of observations contained in their forecast intervals."""
    actual, low, high = _aligned_arrays(y, lower, upper)
    if np.any(low > high):
        raise ValueError("lower bounds must not exceed upper bounds")
    return float(np.mean((actual >= low) & (actual <= high)))


def ece(y: np.ndarray, mean: np.ndarray, std: np.ndarray, bins: int = 10) -> float:
    """Compute binned RMSE versus predicted RMS standard deviation.

    Data are stably sorted by predicted uncertainty, then divided into equal-count
    bins. The returned weighted absolute error is in target units.
    """
    actual, predicted, deviations = _aligned_arrays(y, mean, std)
    if not isinstance(bins, int) or isinstance(bins, bool) or bins < 1:
        raise ValueError("bins must be positive and standard deviations non-negative")
    if np.any(deviations < 0):
        raise ValueError("bins must be positive and standard deviations non-negative")
    order = np.argsort(deviations, kind="stable")
    groups = np.array_split(order, min(bins, len(order)))
    error = 0.0
    for indices in groups:
        rmse = float(np.sqrt(np.mean((actual[indices] - predicted[indices]) ** 2)))
        predicted_scale = float(np.sqrt(np.mean(deviations[indices] ** 2)))
        error += len(indices) / len(order) * abs(rmse - predicted_scale)
    return float(error)


def nll(y: np.ndarray, mean: np.ndarray, std: np.ndarray) -> float:
    """Compute average Gaussian negative log likelihood in nats per observation."""
    actual, predicted, deviations = _aligned_arrays(y, mean, std)
    if np.any(deviations <= 0):
        raise ValueError("standard deviations must be strictly positive")
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        standardized = (actual - predicted) / deviations
        losses = (
            np.log(deviations)
            + 0.5 * standardized**2
            + 0.5 * np.log(2.0 * np.pi)
        )
    return float(np.mean(losses))
