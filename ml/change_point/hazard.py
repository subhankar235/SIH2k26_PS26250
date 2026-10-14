"""Hazard functions used by Bayesian online change-point detection."""

from __future__ import annotations

from collections.abc import Callable

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
    if not 0 < lam <= 1:
        raise ValueError("lam must be in (0, 1]")

    def hazard(run_lengths: np.ndarray) -> np.ndarray:
        """Return a constant hazard vector matching run_lengths shape."""
        return np.full(np.asarray(run_lengths).shape, lam, dtype=float)

    return hazard
