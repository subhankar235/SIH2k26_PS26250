"""Bayesian online change-point detection with a Normal-Gaussian approximation."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np


def bocpd(
    x: np.ndarray,
    hazard: Callable[[np.ndarray], np.ndarray],
    mu0: float = 0.0,
    kappa0: float = 1.0,
    alpha0: float = 1.0,
    beta0: float = 1.0,
) -> np.ndarray:
    """Compute posterior probabilities for each run length at each observation.

    Args:
        x: Finite, one-dimensional observations ordered by event time.
        hazard: Vectorized change probability by current run length.
        mu0: Prior mean for the Normal-Gamma observation model.
        kappa0: Prior mean precision parameter; must be positive.
        alpha0: Prior inverse-gamma shape; must be positive.
        beta0: Prior inverse-gamma scale; must be positive.

    Returns:
        Matrix shaped (n_observations + 1, n_observations + 1), where each row
        contains the posterior probability of each run length after that prefix.

    Raises:
        ValueError: If inputs are not finite one-dimensional values or priors invalid.
    """
    observations = np.asarray(x, dtype=float)
    if observations.ndim != 1 or not np.isfinite(observations).all():
        raise ValueError("x must be a finite one-dimensional array")
    if min(kappa0, alpha0, beta0) <= 0:
        raise ValueError("Normal-Gamma prior parameters must be positive")

    count = len(observations)
    posterior = np.zeros((count + 1, count + 1), dtype=float)
    posterior[0, 0] = 1.0
    means = np.array([mu0], dtype=float)
    kappas = np.array([kappa0], dtype=float)
    alphas = np.array([alpha0], dtype=float)
    betas = np.array([beta0], dtype=float)
    tiny = np.finfo(float).tiny

    for time_index, value in enumerate(observations):
        predictive_variance = betas * (kappas + 1.0) / (alphas * kappas)
        predictive_variance = np.maximum(predictive_variance, tiny)
        standardized = (value - means) ** 2 / predictive_variance
        predictive = np.exp(-0.5 * standardized) / np.sqrt(2.0 * np.pi * predictive_variance)
        run_lengths = np.arange(time_index + 1, dtype=float)
        hazards = np.asarray(hazard(run_lengths), dtype=float)
        if hazards.ndim == 0:
            hazards = np.full(run_lengths.shape, float(hazards))
        if hazards.shape != run_lengths.shape or np.any((hazards < 0) | (hazards > 1)):
            raise ValueError("hazard must return probabilities matching run_lengths")

        joint = posterior[time_index, : time_index + 1] * predictive
        changepoint = np.sum(joint * hazards)
        growth = joint * (1.0 - hazards)
        posterior[time_index + 1, 0] = changepoint
        posterior[time_index + 1, 1 : time_index + 2] = growth
        normalization = posterior[time_index + 1, : time_index + 2].sum()
        if normalization <= tiny:
            posterior[time_index + 1, 0] = 1.0
        else:
            posterior[time_index + 1, : time_index + 2] /= normalization

        updated_kappas = kappas + 1.0
        updated_means = (kappas * means + value) / updated_kappas
        updated_alphas = alphas + 0.5
        updated_betas = betas + (kappas * (value - means) ** 2) / (2.0 * updated_kappas)
        means = np.concatenate(([mu0], updated_means))
        kappas = np.concatenate(([kappa0], updated_kappas))
        alphas = np.concatenate(([alpha0], updated_alphas))
        betas = np.concatenate(([beta0], updated_betas))

    return posterior


def change_points(run_length_posterior: np.ndarray, threshold: float = 0.5) -> list[int]:
    """Extract observation indices whose change-point posterior meets threshold.

    Args:
        run_length_posterior: Matrix returned by :func:`bocpd`.
        threshold: Minimum posterior probability to report.

    Returns:
        Zero-based observation indices with high change-point probability.

    Raises:
        ValueError: If the posterior matrix or threshold is invalid.
    """
    posterior = np.asarray(run_length_posterior, dtype=float)
    if posterior.ndim != 2 or posterior.shape[0] != posterior.shape[1]:
        raise ValueError("run_length_posterior must be a square matrix")
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be in [0, 1]")
    points: list[int] = []
    previous_mode = 0
    for row_index in range(1, posterior.shape[0]):
        row = posterior[row_index, : row_index + 1]
        mode = int(np.argmax(row))
        if row_index > 1 and mode < previous_mode:
            reset_probability = float(row[:previous_mode].sum())
            if reset_probability >= threshold:
                points.append(row_index - 1)
        previous_mode = mode
    return points
