"""Calibration metrics for probabilistic forecasts."""

from __future__ import annotations

import numpy as np

from backend.app.db.models.forecast import Forecast


def _aligned_arrays(
    y: np.ndarray,
    *arrays: np.ndarray,
) -> tuple[np.ndarray, ...]:
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
    """Compute empirical coverage of forecast prediction intervals.

    Args:
        y: Observed values.
        lower: Prediction interval lower bounds.
        upper: Prediction interval upper bounds.

    Returns:
        Fraction of observations contained within their intervals. Empty samples and
        non-finite inputs raise ValueError instead of returning a misleading score.
        Coverage alone is not evidence of calibration; interpret it against the
        interval's nominal confidence level and an independent evaluation sample.

    Raises:
        ValueError: If arrays do not align, are empty, non-finite, or contain invalid intervals.
    """
    actual, low, high = _aligned_arrays(y, lower, upper)
    if np.any(low > high):
        raise ValueError("lower bounds must not exceed upper bounds")
    return float(np.mean((actual >= low) & (actual <= high)))


def ece(y: np.ndarray, mean: np.ndarray, std: np.ndarray, bins: int = 10) -> float:
    """Measure regression scale calibration by binned RMSE versus predicted RMS scale.

    Args:
        y: Observed values.
        mean: Forecast means.
        std: Predicted standard deviations.
        bins: Maximum number of equal-count uncertainty groups.

    Returns:
        Weighted absolute difference, in target units, between empirical RMSE and
        predicted RMS standard deviation. Samples are stably sorted by predicted
        standard deviation and split into at most ``bins`` equal-count groups; ties may
        straddle groups in stable input order. This evaluates scale calibration, not
        bias calibration or every predictive-distribution property.

    Raises:
        ValueError: If arrays are empty, non-finite, misaligned, or scales/bins are invalid.
    """
    actual, predicted, deviations = _aligned_arrays(y, mean, std)
    if not isinstance(bins, int) or isinstance(bins, bool) or bins < 1 or np.any(deviations < 0):
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
        Average Gaussian negative log likelihood in nats per valid (finite) observation.

    Raises:
        ValueError: If arrays are empty/non-finite/misaligned or standard deviations
            are not positive.
    """
    actual, predicted, deviations = _aligned_arrays(y, mean, std)
    if np.any(deviations <= 0):
        raise ValueError("standard deviations must be strictly positive")
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        standardized_residual = (actual - predicted) / deviations
        losses = np.log(deviations) + 0.5 * standardized_residual**2 + 0.5 * np.log(2.0 * np.pi)
    return float(np.mean(losses))


def flag_high_uncertainty(forecast: Forecast, threshold: float) -> bool:
    """Flag forecast intervals wider than a normalized target-scale threshold.

    Args:
        forecast: Persisted forecast containing mean/lower/upper points.
        threshold: Dimensionless maximum ratio ``(upper-lower) / target_scale``.
            The predictor defines target_scale as max(history standard deviation,
            absolute history mean); equality to threshold is not flagged.

    Returns:
        True when any forecast point exceeds the threshold.

    Raises:
        ValueError: If threshold/target scale is invalid or intervals are missing/malformed.
    """
    if not isinstance(threshold, (int, float, np.number)) or isinstance(threshold, bool):
        raise ValueError("uncertainty threshold must be numeric")
    if not np.isfinite(threshold) or threshold < 0:
        raise ValueError("uncertainty threshold must be finite and non-negative")
    target_scale = forecast.calibration_meta.get("target_scale")
    if target_scale is None:
        raise ValueError(
            "forecast does not contain the target scale needed for normalized uncertainty"
        )
    try:
        target_scale = float(target_scale)
    except (TypeError, ValueError) as error:
        raise ValueError("forecast target_scale must be numeric") from error
    if not np.isfinite(target_scale) or target_scale < 0:
        raise ValueError("forecast target_scale must be finite and non-negative")
    if not forecast.points:
        raise ValueError("forecast has no prediction intervals to assess")
    for point in forecast.points:
        try:
            mean = float(point["mean"])
            lower = float(point["lower"])
            upper = float(point["upper"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "forecast point is missing valid mean/lower/upper uncertainty data"
            ) from error
        if not np.isfinite([mean, lower, upper]).all() or lower > mean or mean > upper:
            raise ValueError("forecast interval must be finite and contain its mean")
        width = upper - lower
        relative_width = (
            width / target_scale if target_scale > 0 else (0.0 if width == 0 else float("inf"))
        )
        if relative_width > threshold:
            return True
    return False
