"""Hazard functions used by Bayesian online change-point detection."""

from __future__ import annotations

from collections.abc import Callable
from numbers import Real

import numpy as np


def constant_hazard(lam: float) -> Callable[[np.ndarray], np.ndarray]:
    """Return a constant change probability for every run length.

    Args:
        lam: Per-observation change probability in (0, 1].

    Returns:
        A vectorized function mapping run lengths to hazard probabilities.

    Raises:
        ValueError: If lam is outside (0, 1].
    """
    if isinstance(lam, bool) or not isinstance(lam, Real) or not np.isfinite(lam):
        raise ValueError("lam must be a finite numeric value in (0, 1]")
    if not 0 < lam <= 1:
        raise ValueError("lam must be in (0, 1]")

    def hazard(run_lengths: np.ndarray) -> np.ndarray:
        """Return a constant hazard vector matching run_lengths shape."""
        values = np.asarray(run_lengths)
        if not np.issubdtype(values.dtype, np.number) or not np.isfinite(values).all():
            raise ValueError("run_lengths must contain finite numeric values")
        if np.any(values < 0):
            raise ValueError("run_lengths must be non-negative")
        return np.full(values.shape, float(lam), dtype=float)

    return hazard
