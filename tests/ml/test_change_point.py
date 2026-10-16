"""Tests for stable online Bayesian change-point detection."""

from __future__ import annotations

import numpy as np
import pytest

from ml.change_point.bocpd import bocpd, change_points
from ml.change_point.hazard import constant_hazard


def test_constant_hazard_validates_and_preserves_input_shape() -> None:
    """Return correct hazard arrays and reject invalid probabilities and run lengths."""
    hazard = constant_hazard(0.05)
    run_lengths = np.arange(4, dtype=float)
    assert np.array_equal(hazard(run_lengths), np.full(4, 0.05))
    assert hazard(np.asarray(2.0)).shape == ()
    with pytest.raises(ValueError):
        constant_hazard(float("nan"))
    with pytest.raises(ValueError):
        hazard(np.asarray([-1.0]))


def test_bocpd_rows_are_normalized_and_detect_a_mean_shift() -> None:
    """Posterior rows normalize and a clear abrupt shift changes the run-length mode."""
    observations = np.concatenate((np.zeros(40), np.full(40, 20.0)))
    posterior = bocpd(
        observations,
        constant_hazard(0.02),
        mu0=0.0,
        kappa0=1.0,
        alpha0=4.0,
        beta0=1.0,
    )

    assert posterior.shape == (len(observations) + 1, len(observations) + 1)
    assert np.allclose(posterior.sum(axis=1), 1.0)
    assert np.isfinite(posterior).all()
    assert 40 in change_points(posterior, threshold=0.5)


def test_bocpd_rejects_invalid_hazard_output_and_posterior() -> None:
    """Validate run-length hazard outputs and change-point thresholds."""
    with pytest.raises(ValueError, match="hazard"):
        bocpd(np.asarray([1.0]), lambda run_lengths: np.full(run_lengths.shape, np.nan))
    with pytest.raises(ValueError, match="finite one-dimensional"):
        bocpd(np.asarray([[1.0]]), constant_hazard(0.1))
    with pytest.raises(ValueError, match="threshold"):
        change_points(np.eye(2), threshold=float("nan"))
