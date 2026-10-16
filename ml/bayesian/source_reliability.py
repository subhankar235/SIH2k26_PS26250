"""Hierarchical Bayesian estimation of per-source agreement reliability."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    import arviz as az


def _validate_observations(observations: pd.DataFrame) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Validate source-level agreement counts and return aligned arrays."""
    required = {"source_id", "successes", "failures"}
    missing = required - set(observations.columns)
    if missing:
        raise ValueError(f"observations are missing columns: {sorted(missing)}")
    if observations.empty:
        raise ValueError("observations must include at least one source")
    if observations["source_id"].isna().any():
        raise ValueError("source_id values must not be missing")
    source_ids = observations["source_id"].astype(str).tolist()
    if any(not value for value in source_ids) or len(set(source_ids)) != len(source_ids):
        raise ValueError("source_id values must be non-empty and unique")
    counts: list[np.ndarray] = []
    for column in ("successes", "failures"):
        values = pd.to_numeric(observations[column], errors="coerce").to_numpy(dtype=float)
        valid_counts = (
            np.isfinite(values).all()
            and not (values < 0).any()
            and np.equal(values, np.floor(values)).all()
        )
        if not valid_counts:
            raise ValueError(f"{column} must contain finite non-negative integer counts")
        counts.append(values.astype(np.int64))
    return source_ids, counts[0], counts[1]


def fit(
    observations: pd.DataFrame,
    seed: int,
    draws: int = 1000,
    tune: int = 1000,
) -> az.InferenceData:
    """Fit a hierarchical Beta-Binomial model of source agreement reliability.

    Each source's reliability is drawn from a shared Beta population. Its observed
    agreement and disagreement counts update that source-level latent probability.
    PyMC's NUTS sampler returns a complete ArviZ inference object with source labels.

    Args:
        observations: DataFrame with unique ``source_id`` and integer ``successes`` /
            ``failures`` columns.
        seed: Non-negative deterministic PyMC random seed.
        draws: Posterior draws per chain.
        tune: Warm-up draws per chain.

    Returns:
        An ArviZ InferenceData with posterior variables ``reliability``,
        ``population_mean``, and ``concentration``.

    Raises:
        ImportError: If PyMC or ArviZ is not installed.
        ValueError: If data or sampler arguments are invalid.
    """
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if not isinstance(draws, int) or isinstance(draws, bool) or draws < 2:
        raise ValueError("draws must be an integer of at least 2")
    if not isinstance(tune, int) or isinstance(tune, bool) or tune < 0:
        raise ValueError("tune must be a non-negative integer")
    source_ids, successes, failures = _validate_observations(observations)
    try:
        import arviz as az
        import pymc as pm
    except ImportError as error:
        raise ImportError(
            "Bayesian source reliability requires PyMC and ArviZ; "
            "install the optional dependencies from ml/requirements.txt"
        ) from error

    coordinates = {"source": source_ids}
    with pm.Model(coords=coordinates):
        population_mean = pm.Beta("population_mean", alpha=2.0, beta=2.0)
        concentration = pm.Gamma("concentration", alpha=2.0, beta=0.1)
        reliability = pm.Beta(
            "reliability",
            alpha=population_mean * concentration,
            beta=(1.0 - population_mean) * concentration,
            dims="source",
        )
        pm.Binomial(
            "agreement_observations",
            n=successes + failures,
            p=reliability,
            observed=successes,
            dims="source",
        )
        inference_data = pm.sample(
            draws=draws,
            tune=tune,
            chains=4,
            cores=1,
            random_seed=seed,
            target_accept=0.9,
            progressbar=False,
            return_inferencedata=True,
        )
    if not isinstance(inference_data, az.InferenceData):
        raise TypeError("PyMC did not return an ArviZ InferenceData result")
    return inference_data
