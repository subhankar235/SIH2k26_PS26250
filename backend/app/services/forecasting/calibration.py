"""Forecast uncertainty metrics shared with the ML evaluation package."""

from __future__ import annotations

import numpy as np

from backend.app.db.models.forecast import Forecast
from ml.forecasting.calibration import coverage, ece, nll

__all__ = ["coverage", "ece", "flag_high_uncertainty", "nll"]


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
        ValueError: If threshold/target scale is invalid or intervals are malformed.
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
