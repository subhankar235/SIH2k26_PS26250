"""Convergence and sampling-quality checks for ArviZ posterior traces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import arviz as az


@dataclass(frozen=True)
class DiagnosticsReport:
    """Aggregate convergence diagnostics for all sampled posterior variables."""

    max_r_hat: float
    min_ess_bulk: float
    divergences: int
    converged: bool


def _finite_extreme(dataset: object, *, maximum: bool) -> float:
    """Reduce numeric dataset variables to their finite maximum or minimum."""
    values: list[np.ndarray] = []
    data_vars = getattr(dataset, "data_vars", None)
    if data_vars is None:
        raise ValueError("ArviZ diagnostic did not return a labeled dataset")
    for variable in data_vars.values():
        array = np.asarray(variable.values, dtype=np.float64)
        values.append(array[np.isfinite(array)])
    finite = [array for array in values if array.size]
    if not finite:
        return float("inf") if maximum else 0.0
    combined = np.concatenate(finite)
    return float(np.max(combined) if maximum else np.min(combined))


def check(idata: az.InferenceData) -> DiagnosticsReport:
    """Check rank-normalized R-hat, bulk ESS, and NUTS divergences.

    Convergence passes when every finite posterior variable has max R-hat < 1.01,
    minimum bulk effective sample size >= 100, and no divergent transitions.
    """
    if not hasattr(idata, "posterior") or not idata.posterior.data_vars:
        raise ValueError("inference data must contain at least one posterior variable")
    try:
        import arviz as az
    except ImportError as error:
        raise ImportError("Bayesian diagnostics require ArviZ") from error
    rhat = _finite_extreme(az.rhat(idata, method="rank"), maximum=True)
    ess = _finite_extreme(az.ess(idata, method="bulk"), maximum=False)
    sample_stats = getattr(idata, "sample_stats", None)
    divergences = 0
    if sample_stats is not None and "diverging" in sample_stats:
        divergences = int(np.asarray(sample_stats["diverging"].values, dtype=np.int64).sum())
    converged = bool(rhat < 1.01 and ess >= 100 and divergences == 0)
    return DiagnosticsReport(
        max_r_hat=rhat,
        min_ess_bulk=ess,
        divergences=divergences,
        converged=converged,
    )
