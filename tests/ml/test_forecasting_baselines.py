"""Tests for probabilistic forecasting baselines and shared calibration metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.forecasting.baselines.arima import fit_predict as arima_fit_predict
from ml.forecasting.baselines.lstm import fit_predict as lstm_fit_predict
from ml.forecasting.baselines.sparse_gp import fit_predict as sparse_gp_fit_predict
from ml.forecasting.calibration import coverage, ece, nll


def _series() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create a seeded smooth series and a three-step feature frame."""
    x = np.arange(48, dtype=float)
    train = pd.DataFrame({"target": 10.0 + 0.2 * x + np.sin(x / 4.0)})
    test = pd.DataFrame(
        {
            "target_lag_1": [train.target.iloc[-1], train.target.iloc[-1], train.target.iloc[-1]],
            "target_lag_2": [train.target.iloc[-2]] * 3,
            "forecast_horizon_step": [1.0, 2.0, 3.0],
        }
    )
    return train, test


@pytest.mark.parametrize(
    "fit_predict",
    [arima_fit_predict, lstm_fit_predict, sparse_gp_fit_predict],
    ids=["arima", "lstm", "sparse-gp"],
)
def test_forecasting_baselines_return_finite_ordered_prediction_intervals(fit_predict) -> None:
    """Each baseline returns one finite interval containing each recursive mean."""
    train, test = _series()
    result = fit_predict(train, test, seed=73)
    assert result.mean.shape == result.lower.shape == result.upper.shape == (3,)
    assert np.isfinite(result.mean).all()
    assert np.isfinite(result.lower).all() and np.isfinite(result.upper).all()
    assert np.all(result.lower <= result.mean)
    assert np.all(result.mean <= result.upper)


def test_learned_baselines_are_reproducible_for_a_fixed_seed() -> None:
    """LSTM and sparse-GP forecasts are repeatable under the same explicit seed."""
    train, test = _series()
    for fit_predict in (lstm_fit_predict, sparse_gp_fit_predict):
        first = fit_predict(train, test, seed=91)
        second = fit_predict(train, test, seed=91)
        assert np.allclose(first.mean, second.mean)
        assert np.allclose(first.lower, second.lower)
        assert np.allclose(first.upper, second.upper)


def test_shared_calibration_metrics_validate_and_match_documented_semantics() -> None:
    """Compute interval coverage, uncertainty scale ECE, and Gaussian NLL."""
    observed = np.asarray([1.0, 2.0, 3.0])
    mean = np.asarray([1.0, 2.0, 2.0])
    std = np.asarray([0.5, 0.5, 1.0])
    assert coverage(observed, mean - 1.0, mean + 1.0) == 1.0
    assert ece(observed, mean, std, bins=2) >= 0.0
    assert np.isfinite(nll(observed, mean, std))
    with pytest.raises(ValueError, match="strictly positive"):
        nll(observed, mean, np.asarray([0.5, 0.0, 1.0]))


def test_backend_service_imports_shared_calibration_implementations() -> None:
    """Keep service and ML evaluation metric implementations identical."""
    from backend.app.services.forecasting import calibration as backend_calibration

    assert backend_calibration.coverage is coverage
    assert backend_calibration.ece is ece
    assert backend_calibration.nll is nll
