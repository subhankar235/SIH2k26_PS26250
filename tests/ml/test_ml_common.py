"""Reproducibility and MLflow helper contract tests."""

from __future__ import annotations

import random
import sys
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
import torch

from ml.common.mlflow_utils import log_artifact_path, log_metrics, start_run
from ml.common.seed import set_all_seeds


def test_set_all_seeds_reproduces_python_numpy_and_torch_streams() -> None:
    """Reset all available CPU RNG streams to exactly the same seeded samples."""
    set_all_seeds(922)
    first = (random.random(), np.random.random(), torch.rand(3))
    set_all_seeds(922)
    second = (random.random(), np.random.random(), torch.rand(3))

    assert first[0] == second[0]
    assert first[1] == second[1]
    assert torch.equal(first[2], second[2])
    with pytest.raises(TypeError):
        set_all_seeds(True)
    with pytest.raises(ValueError):
        set_all_seeds(-1)


def test_mlflow_helpers_start_log_and_close_active_run(monkeypatch, tmp_path: Path) -> None:
    """Record run params/tags, finite metrics, and file/directory artifacts."""
    calls: list[tuple[str, object]] = []
    run = SimpleNamespace(info=SimpleNamespace(run_id="fake-run"))
    fake = ModuleType("mlflow")
    fake.set_experiment = lambda name: (  # type: ignore[attr-defined]
        calls.append(("experiment", name)) or SimpleNamespace(experiment_id="e-1")
    )
    fake.start_run = lambda **kwargs: (  # type: ignore[attr-defined]
        calls.append(("start", kwargs)) or nullcontext(run)
    )
    fake.log_params = lambda values: calls.append(("params", values))  # type: ignore[attr-defined]
    fake.set_tags = lambda values: calls.append(("tags", values))  # type: ignore[attr-defined]
    fake.log_metrics = lambda values, step=None: calls.append(  # type: ignore[attr-defined]
        ("metrics", (values, step))
    )
    fake.log_artifact = lambda value: calls.append(("artifact", value))  # type: ignore[attr-defined]
    fake.log_artifacts = lambda value: calls.append(("artifacts", value))  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mlflow", fake)

    artifact_file = tmp_path / "weights.bin"
    artifact_file.write_bytes(b"weights")
    artifact_dir = tmp_path / "bundle"
    artifact_dir.mkdir()
    with start_run(
        "ditto-test", {"seed": 11, "config": {"lr": 0.01}}, {"model": "ditto"}
    ) as active:
        assert active is run
        log_metrics({"f1": 0.8}, step=2)
        log_artifact_path(artifact_file)
        log_artifact_path(artifact_dir)

    assert calls[0] == ("experiment", "ditto-test")
    assert calls[1] == ("start", {"experiment_id": "e-1"})
    assert ("metrics", ({"f1": 0.8}, 2)) in calls
    assert ("artifact", str(artifact_file)) in calls
    assert ("artifacts", str(artifact_dir)) in calls
    with pytest.raises(ValueError, match="finite"):
        log_metrics({"nan": float("nan")})
    with pytest.raises(FileNotFoundError):
        log_artifact_path(tmp_path / "missing")
