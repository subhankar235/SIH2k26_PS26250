"""End-to-end tests for DS-DGP training, persistence, and predictive uncertainty."""

from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def test_ds_dgp_trains_saves_loads_and_predicts_real_intervals(
    tmp_path: Path, monkeypatch
) -> None:
    """Fit actual variational GP weights and reload their calibrated predictive pipeline."""
    pytest.importorskip("gpytorch")
    import ml.forecasting.ds_dgp.train as train_module
    from ml.forecasting.ds_dgp.model import load_model, predict

    monkeypatch.setattr(train_module, "start_run", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(train_module, "log_metrics", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(train_module, "log_artifact_path", lambda *_args, **_kwargs: None)
    train_path = tmp_path / "train.csv"
    validation_path = tmp_path / "validation.csv"
    test_path = tmp_path / "test.csv"
    for path, start, count in ((train_path, 0, 16), (validation_path, 16, 5), (test_path, 21, 5)):
        x = np.arange(start, start + count, dtype=float)
        pd.DataFrame({"feature": x, "target": 2.0 * x + np.sin(x / 3)}).to_csv(path, index=False)

    artifact = train_module.train(
        train_module.DSDGPConfig(
            train_path=train_path,
            validation_path=validation_path,
            test_path=test_path,
            target="target",
            feature_columns=("feature",),
            output_dir=tmp_path / "ds-dgp-artifact",
            epochs=1,
            batch_size=8,
            hidden_dims=(4,),
            num_inducing=5,
            num_likelihood_samples=2,
            experiment="test-ds-dgp",
        ),
        seed=23,
    )

    metadata = json.loads((artifact / "metadata.json").read_text(encoding="utf-8"))
    model = load_model(artifact)
    mean, lower, upper = predict(model, pd.DataFrame({"feature": [22.0, 23.0]}), seed=8)
    assert (artifact / "model.pt").is_file()
    assert metadata["hidden_dims"] == [4]
    assert metadata["validation_metrics"]["rmse"] >= 0
    assert mean.shape == lower.shape == upper.shape == (2,)
    assert np.isfinite(mean).all() and np.all(lower <= mean) and np.all(mean <= upper)
    repeated = predict(model, pd.DataFrame({"feature": [22.0, 23.0]}), seed=8)
    assert np.allclose(mean, repeated[0])
