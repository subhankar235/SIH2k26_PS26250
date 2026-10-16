"""Numerically stable Bayesian online change-point detection."""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np


def _logsumexp(values: np.ndarray) -> float:
    """Compute log(sum(exp(values))) safely for a one-dimensional array."""
    maximum = float(np.max(values))
    if not np.isfinite(maximum):
        return maximum
    return maximum + math.log(float(np.exp(values - maximum).sum()))


def bocpd(
    x: np.ndarray,
    hazard: Callable[[np.ndarray], np.ndarray],
    mu0: float = 0.0,
    kappa0: float = 1.0,
    alpha0: float = 1.0,
    beta0: float = 1.0,
) -> np.ndarray:
    """Compute Normal-Gamma BOCPD posterior probabilities for all run lengths.

    The observation model uses the exact Student-t predictive density implied by
    a Normal-Gamma prior. Recursion is performed in log space to remain stable on
    long or highly unlikely sequences.
    """
    observations = np.asarray(x, dtype=float)
    if observations.ndim != 1 or not np.isfinite(observations).all():
        raise ValueError("x must be a finite one-dimensional array")
    prior_values = np.asarray([mu0, kappa0, alpha0, beta0], dtype=float)
    if not np.isfinite(prior_values).all():
        raise ValueError("Normal-Gamma prior parameters must be finite")
    if min(kappa0, alpha0, beta0) <= 0:
        raise ValueError("Normal-Gamma prior parameters kappa0, alpha0, beta0 must be positive")

    count = len(observations)
    posterior = np.zeros((count + 1, count + 1), dtype=float)
    posterior[0, 0] = 1.0
    log_posterior = np.full_like(posterior, -np.inf)
    log_posterior[0, 0] = 0.0
    means = np.asarray([mu0], dtype=float)
    kappas = np.asarray([kappa0], dtype=float)
    alphas = np.asarray([alpha0], dtype=float)
    betas = np.asarray([beta0], dtype=float)

    for time_index, value in enumerate(observations):
        run_lengths = np.arange(time_index + 1, dtype=float)
        hazards = np.asarray(hazard(run_lengths), dtype=float)
        if hazards.ndim == 0:
            hazards = np.full(run_lengths.shape, float(hazards))
        if (
            hazards.shape != run_lengths.shape
            or not np.isfinite(hazards).all()
            or np.any((hazards < 0) | (hazards > 1))
        ):
            raise ValueError("hazard must return finite probabilities matching run_lengths")

        # Student-t posterior predictive density under the Normal-Gamma model.
        log_predictive = (
            np.fromiter(
                (math.lgamma(float(alpha + 0.5)) - math.lgamma(float(alpha)) for alpha in alphas),
                dtype=float,
                count=len(alphas),
            )
            + 0.5 * np.log(kappas / (2.0 * np.pi * betas * (kappas + 1.0)))
            - (alphas + 0.5)
            * np.log1p(kappas * (value - means) ** 2 / (2.0 * betas * (kappas + 1.0)))
        )
        log_joint = log_posterior[time_index, : time_index + 1] + log_predictive
        log_hazard = np.full_like(hazards, -np.inf)
        log_growth_hazard = np.full_like(hazards, -np.inf)
        positive_hazard = hazards > 0
        below_one_hazard = hazards < 1
        log_hazard[positive_hazard] = np.log(hazards[positive_hazard])
        log_growth_hazard[below_one_hazard] = np.log1p(-hazards[below_one_hazard])

        log_posterior[time_index + 1, 0] = _logsumexp(log_joint + log_hazard)
        log_posterior[time_index + 1, 1 : time_index + 2] = (
            log_joint + log_growth_hazard
        )
        row_log_normalizer = _logsumexp(log_posterior[time_index + 1, : time_index + 2])
        if not np.isfinite(row_log_normalizer):
            raise FloatingPointError("BOCPD posterior could not be normalized")
        log_posterior[time_index + 1, : time_index + 2] -= row_log_normalizer
        posterior[time_index + 1, : time_index + 2] = np.exp(
            log_posterior[time_index + 1, : time_index + 2]
        )

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
    """Return indexes where posterior mass supports a run-length reset.

    Under a constant hazard, posterior mass at run length zero equals the hazard
    itself and therefore is not a data-driven change score. A detected reset is
    instead a drop in the modal run length with sufficient posterior mass on run
    lengths shorter than the previous mode.
    """
    posterior = np.asarray(run_length_posterior, dtype=float)
    if posterior.ndim != 2 or posterior.shape[0] != posterior.shape[1]:
        raise ValueError("run_length_posterior must be a square matrix")
    if not np.isfinite(posterior).all() or np.any(posterior < 0):
        raise ValueError("run_length_posterior must contain finite non-negative values")
    if isinstance(threshold, bool) or not np.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("threshold must be a finite value in [0, 1]")
    points: list[int] = []
    previous_mode = 0
    for row_index in range(1, len(posterior)):
        row = posterior[row_index, : row_index + 1]
        mode = int(np.argmax(row))
        if row_index > 1 and mode < previous_mode:
            reset_probability = float(row[:previous_mode].sum())
            if reset_probability >= threshold:
                points.append(row_index - 1)
        previous_mode = mode
    return points
