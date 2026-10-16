"""Tests for Bayesian source reliability, claim inference, and diagnostics."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from ml.bayesian.claim_posterior import ClaimObs, posterior_for_claims
from ml.bayesian.diagnostics import check
from ml.bayesian.source_reliability import _validate_observations, fit


class _PosteriorVariable:
    """Minimal labeled-array surface used to test posterior claim calculations."""

    dims = ("chain", "draw", "source")

    def __init__(self, values: np.ndarray) -> None:
        self.values = values

    def transpose(self, *_dims: str) -> _PosteriorVariable:
        return self


class _Posterior(dict):
    """Dictionary-like posterior dataset with labeled source coordinates."""

    def __init__(self, values: np.ndarray, sources: list[str]) -> None:
        super().__init__(reliability=_PosteriorVariable(values))
        self.coords = {"source": SimpleNamespace(values=np.asarray(sources))}
        self.data_vars = self


class _InferenceData:
    """Small test inference container that mirrors ArviZ's posterior groups."""

    def __init__(self, values: np.ndarray, sources: list[str]) -> None:
        self.posterior = _Posterior(values, sources)


def test_validate_source_observation_counts() -> None:
    """Require unique source identifiers and valid non-negative integer counts."""
    source_ids, successes, failures = _validate_observations(
        pd.DataFrame(
            {"source_id": ["feed-a", "feed-b"], "successes": [9, 2], "failures": [1, 3]}
        )
    )
    assert source_ids == ["feed-a", "feed-b"]
    assert successes.tolist() == [9, 2]
    assert failures.tolist() == [1, 3]
    with pytest.raises(ValueError, match="unique"):
        _validate_observations(
            pd.DataFrame(
                {"source_id": ["same", "same"], "successes": [1, 2], "failures": [0, 0]}
            )
        )
    with pytest.raises(ValueError, match="integer counts"):
        _validate_observations(
            pd.DataFrame({"source_id": ["feed"], "successes": [1.2], "failures": [0]})
        )


def test_claim_posterior_combines_competing_source_reliability_draws() -> None:
    """A high-reliability source should support its value over a low-reliability rival."""
    idata = _InferenceData(
        np.asarray(
            [
                [[0.9, 0.55]],
                [[0.92, 0.52]],
                [[0.88, 0.58]],
                [[0.91, 0.54]],
            ]
        ),
        ["trusted", "noisy"],
    )
    claims = [
        ClaimObs("claim-1", "trusted", "entity-1", "capacity", 100),
        ClaimObs("claim-2", "noisy", "entity-1", "capacity", 200),
    ]

    posterior = posterior_for_claims(idata, claims)

    assert posterior[0].claim_id == "claim-1"
    assert posterior[0].probability > 0.8
    assert posterior[1].probability < 0.2
    assert all(0 <= item.hdi_low <= item.probability <= item.hdi_high <= 1 for item in posterior)


def test_claim_posterior_rejects_claims_without_source_draws() -> None:
    """Do not silently invent a source reliability for unsupported claims."""
    idata = _InferenceData(np.full((2, 4, 1), 0.8), ["known"])
    with pytest.raises(ValueError, match="without posterior estimates"):
        posterior_for_claims(
            idata,
            [ClaimObs("claim", "unknown", "entity", "attribute", "value")],
        )


def test_diagnostics_apply_rhat_ess_and_divergence_thresholds(monkeypatch) -> None:
    """Pass only converged chains with adequate effective sample size and no divergences."""
    fake_arviz = ModuleType("arviz")
    fake_arviz.rhat = lambda *_args, **_kwargs: SimpleNamespace(
        data_vars={"reliability": SimpleNamespace(values=np.asarray([1.005, 1.008]))}
    )  # type: ignore[attr-defined]
    fake_arviz.ess = lambda *_args, **_kwargs: SimpleNamespace(
        data_vars={"reliability": SimpleNamespace(values=np.asarray([150.0, 240.0]))}
    )  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "arviz", fake_arviz)
    idata = SimpleNamespace(
        posterior=SimpleNamespace(data_vars={"reliability": object()}),
        sample_stats={"diverging": SimpleNamespace(values=np.zeros((4, 50), dtype=int))},
    )

    report = check(idata)

    assert report.max_r_hat == pytest.approx(1.008)
    assert report.min_ess_bulk == pytest.approx(150.0)
    assert report.divergences == 0
    assert report.converged
    idata.sample_stats["diverging"].values[0, 0] = 1
    assert not check(idata).converged


def test_fit_rejects_invalid_sampler_arguments_before_optional_import() -> None:
    """Validate public sampling arguments even where PyMC is not installed."""
    observations = pd.DataFrame({"source_id": ["feed"], "successes": [1], "failures": [0]})
    with pytest.raises(ValueError, match="non-negative"):
        fit(observations, seed=-1)
    with pytest.raises(ValueError, match="at least 2"):
        fit(observations, seed=4, draws=1)


def test_real_pymc_fit_claim_posteriors_and_diagnostics(monkeypatch) -> None:
    """Execute NUTS and check the real ArviZ output through the full Bayesian path."""
    monkeypatch.setenv("PYTENSOR_FLAGS", "cxx=")
    pytest.importorskip("pymc")
    pytest.importorskip("arviz")
    observations = pd.DataFrame(
        {
            "source_id": ["trusted", "noisy"],
            "successes": [18, 6],
            "failures": [2, 14],
        }
    )
    inference_data = fit(observations, seed=27, draws=100, tune=100)

    posterior = posterior_for_claims(
        inference_data,
        [
            ClaimObs("trusted-claim", "trusted", "asset", "capacity", 100),
            ClaimObs("noisy-claim", "noisy", "asset", "capacity", 200),
        ],
    )
    report = check(inference_data)

    assert inference_data.posterior["reliability"].shape == (4, 100, 2)
    assert posterior[0].probability > posterior[1].probability
    assert report.max_r_hat >= 1.0
    assert report.min_ess_bulk > 0
    assert report.divergences >= 0
