"""Train and track a seeded doubly stochastic deep Gaussian process."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import gpytorch
import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader, TensorDataset

from ml.common.mlflow_utils import log_artifact_path, log_metrics, start_run
from ml.common.seed import set_all_seeds
from ml.forecasting.ds_dgp.model import DSDGP, predict


@dataclass(frozen=True)
class DSDGPConfig:
    """Time-series data paths, feature schema, and variational optimization settings."""

    data_path: Path | None = None
    train_path: Path | None = None
    validation_path: Path | None = None
    test_path: Path | None = None
    target: str = "target"
    feature_columns: tuple[str, ...] | None = None
    output_dir: Path = Path("ml/artifacts/ds_dgp")
    epochs: int = 50
    batch_size: int = 64
    learning_rate: float = 0.01
    hidden_dims: tuple[int, ...] = (16, 16)
    num_inducing: int = 64
    num_likelihood_samples: int = 8
    experiment: str = "forecasting-ds-dgp"

    def __post_init__(self) -> None:
        if not self.target.strip() or not self.experiment.strip():
            raise ValueError("target and experiment must be non-empty strings")
        if self.data_path is None and self.train_path is None:
            raise ValueError("configure data_path or train_path")
        if self.train_path is not None and self.data_path is not None:
            raise ValueError("use data_path or train_path, not both")
        if self.epochs < 1 or self.batch_size < 1 or self.num_inducing < 2:
            raise ValueError("epochs/batch_size must be positive and num_inducing >= 2")
        if self.num_likelihood_samples < 1:
            raise ValueError("num_likelihood_samples must be positive")
        if not np.isfinite(self.learning_rate) or self.learning_rate <= 0:
            raise ValueError("learning_rate must be finite and positive")
        if len(self.hidden_dims) not in {1, 2} or any(width < 1 for width in self.hidden_dims):
            raise ValueError("hidden_dims must specify one or two positive hidden layers")
        if self.feature_columns is not None and (
            not self.feature_columns or len(set(self.feature_columns)) != len(self.feature_columns)
        ):
            raise ValueError("feature_columns must be non-empty and unique")


def _read_frame(path: Path) -> pd.DataFrame:
    """Read CSV or Parquet data and preserve chronological ordering."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.casefold() in {".parquet", ".pq"}:
        frame = pd.read_parquet(path)
    else:
        frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f"forecast dataset is empty: {path}")
    if "event_time" in frame:
        timestamps = pd.to_datetime(frame["event_time"], utc=True, errors="coerce")
        if timestamps.isna().any():
            raise ValueError(f"dataset contains invalid event_time values: {path}")
        frame = frame.assign(__time_sort=timestamps).sort_values(
            "__time_sort", kind="stable"
        ).drop(columns="__time_sort").reset_index(drop=True)
    return frame


def _load_splits(cfg: DSDGPConfig) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    """Load explicit chronological splits or split one ordered dataset 80/20."""
    if cfg.train_path is not None:
        train = _read_frame(Path(cfg.train_path))
        validation = _read_frame(Path(cfg.validation_path)) if cfg.validation_path else None
        test = _read_frame(Path(cfg.test_path)) if cfg.test_path else None
        if validation is None:
            if len(train) < 5:
                raise ValueError("at least five training rows are needed for a temporal holdout")
            boundary = max(2, int(len(train) * 0.8))
            validation = train.iloc[boundary:].reset_index(drop=True)
            train = train.iloc[:boundary].reset_index(drop=True)
        return train, validation, test

    frame = _read_frame(Path(cfg.data_path))  # type: ignore[arg-type]
    if len(frame) < 5:
        raise ValueError("at least five rows are needed for a temporal 80/20 split")
    boundary = max(2, int(len(frame) * 0.8))
    return frame.iloc[:boundary].reset_index(drop=True), frame.iloc[boundary:].reset_index(
        drop=True
    ), None


def _target_values(frame: pd.DataFrame, target: str) -> np.ndarray:
    """Read a finite one-dimensional numeric target column."""
    if target not in frame:
        raise ValueError(f"dataset is missing target column {target!r}")
    values = pd.to_numeric(frame[target], errors="coerce").to_numpy(dtype=np.float32)
    if not np.isfinite(values).all():
        raise ValueError(f"target {target!r} contains missing or non-finite values")
    return values


def _select_features(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame | None,
    target: str,
    configured: tuple[str, ...] | None,
) -> tuple[tuple[str, ...], np.ndarray, np.ndarray, np.ndarray | None]:
    """Select numeric past-only features and build finite arrays for each split."""
    if configured is not None:
        columns = tuple(configured)
    else:
        columns = tuple(
            column
            for column in train.select_dtypes(include=[np.number]).columns
            if column != target
        )
        if not columns:
            columns = ("__time_index",)

    def matrix(frame: pd.DataFrame, offset: int) -> np.ndarray:
        if columns == ("__time_index",):
            return np.arange(offset, offset + len(frame), dtype=np.float32).reshape(-1, 1)
        missing = set(columns) - set(frame.columns)
        if missing:
            raise ValueError(f"dataset is missing configured features: {sorted(missing)}")
        try:
            values = frame.loc[:, list(columns)].apply(pd.to_numeric, errors="raise").to_numpy(
                dtype=np.float32
            )
        except (TypeError, ValueError) as error:
            raise ValueError("DS-DGP features must be numeric") from error
        if not np.isfinite(values).all():
            raise ValueError("DS-DGP features must not contain missing or non-finite values")
        return values

    train_x = matrix(train, 0)
    validation_x = matrix(validation, len(train))
    test_x = matrix(test, len(train) + len(validation)) if test is not None else None
    return columns, train_x, validation_x, test_x


def _metrics(
    y: np.ndarray,
    mean: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> dict[str, float]:
    """Calculate predictive RMSE, MAE, and empirical interval coverage."""
    return {
        "rmse": float(np.sqrt(np.mean((y - mean) ** 2))),
        "mae": float(np.mean(np.abs(y - mean))),
        "coverage_95": float(np.mean((y >= lower) & (y <= upper))),
    }


def train(cfg: DSDGPConfig | dict[str, Any], seed: int) -> Path:
    """Train a doubly stochastic deep GP and save reloadable model/scaler artifacts."""
    if isinstance(cfg, dict):
        values = dict(cfg)
        values.pop("seed", None)  # The seed is supplied separately to train().
        if "lr" in values:
            values["learning_rate"] = values.pop("lr")
        if values.get("feature_columns") is not None:
            values["feature_columns"] = tuple(values["feature_columns"])
        if values.get("hidden_dims") is not None:
            values["hidden_dims"] = tuple(values["hidden_dims"])
        for name in ("data_path", "train_path", "validation_path", "test_path", "output_dir"):
            if values.get(name) is not None:
                values[name] = Path(values[name])
        cfg = DSDGPConfig(**values)
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    set_all_seeds(seed)
    train_frame, validation_frame, test_frame = _load_splits(cfg)
    if len(train_frame) < 2 or validation_frame.empty:
        raise ValueError("training and validation splits must both contain data")
    y_train_raw = _target_values(train_frame, cfg.target)
    y_validation = _target_values(validation_frame, cfg.target)
    y_test = _target_values(test_frame, cfg.target) if test_frame is not None else None
    feature_columns, x_train_raw, x_validation_raw, x_test_raw = _select_features(
        train_frame,
        validation_frame,
        test_frame,
        cfg.target,
        cfg.feature_columns,
    )
    x_mean = x_train_raw.mean(axis=0)
    x_scale = x_train_raw.std(axis=0)
    x_scale[x_scale < 1e-8] = 1.0
    y_mean = float(y_train_raw.mean())
    y_scale = float(y_train_raw.std())
    if y_scale < 1e-8:
        y_scale = 1.0
    x_train = torch.from_numpy((x_train_raw - x_mean) / x_scale)
    y_train = torch.from_numpy((y_train_raw - y_mean) / y_scale)
    model = DSDGP(
        input_dims=x_train.shape[1],
        hidden_dims=cfg.hidden_dims,
        num_inducing=min(cfg.num_inducing, len(x_train)),
        x_mean=x_mean,
        x_scale=x_scale,
        y_mean=y_mean,
        y_scale=y_scale,
        num_likelihood_samples=cfg.num_likelihood_samples,
    )
    model.feature_columns = feature_columns
    model.training_rows = len(train_frame)
    model.seed = seed
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.learning_rate)
    generator = torch.Generator().manual_seed(seed)
    loader = DataLoader(
        TensorDataset(x_train, y_train),
        batch_size=min(cfg.batch_size, len(x_train)),
        shuffle=True,
        generator=generator,
    )
    objective = gpytorch.mlls.DeepApproximateMLL(
        gpytorch.mlls.VariationalELBO(model.likelihood, model, num_data=len(x_train))
    )
    losses: list[float] = []
    for _epoch in range(cfg.epochs):
        model.train()
        model.likelihood.train()
        batch_losses: list[float] = []
        for features, targets in loader:
            optimizer.zero_grad(set_to_none=True)
            with gpytorch.settings.num_likelihood_samples(cfg.num_likelihood_samples):
                loss = -objective(model(features), targets)
            if not torch.isfinite(loss):
                raise FloatingPointError("DS-DGP training produced a non-finite objective")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=10.0)
            optimizer.step()
            batch_losses.append(float(loss.detach().cpu()))
        losses.append(float(np.mean(batch_losses)))

    validation_mean, validation_lower, validation_upper = predict(
        model, x_validation_raw, seed=seed
    )
    validation_metrics = _metrics(y_validation, validation_mean, validation_lower, validation_upper)
    test_metrics: dict[str, float] | None = None
    if test_frame is not None and y_test is not None and x_test_raw is not None:
        test_mean, test_lower, test_upper = predict(model, x_test_raw, seed=seed)
        test_metrics = _metrics(y_test, test_mean, test_lower, test_upper)

    output_dir = Path(cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, Any] = {
        "model": "DSDGP",
        "seed": seed,
        "input_dims": int(x_train.shape[1]),
        "hidden_dims": list(cfg.hidden_dims),
        "num_inducing": model.num_inducing,
        "num_likelihood_samples": cfg.num_likelihood_samples,
        "feature_columns": list(feature_columns),
        "target": cfg.target,
        "x_mean": x_mean.tolist(),
        "x_scale": x_scale.tolist(),
        "y_mean": y_mean,
        "y_scale": y_scale,
        "training_rows": len(train_frame),
        "validation_rows": len(validation_frame),
        "test_rows": len(test_frame) if test_frame is not None else 0,
        "epoch_losses": losses,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
    }
    params = {**asdict(cfg), "seed": seed}
    with start_run(cfg.experiment, params, tags={"model": "ds_dgp", "seed": str(seed)}):
        log_metrics({f"validation_{key}": value for key, value in validation_metrics.items()})
        if test_metrics is not None:
            log_metrics({f"test_{key}": value for key, value in test_metrics.items()})
        log_metrics({"final_training_loss": losses[-1]})
        torch.save(model.state_dict(), output_dir / "model.pt")
        (output_dir / "metadata.json").write_text(
            json.dumps(metadata, sort_keys=True, indent=2), encoding="utf-8"
        )
        log_artifact_path(output_dir)
    return output_dir


def main() -> None:
    """Load YAML settings and train using the documented ``--config --seed`` CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    import yaml

    raw = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("DS-DGP YAML config must contain a mapping")
    config_seed = args.seed if args.seed is not None else raw.get("seed")
    if config_seed is None:
        raise ValueError("provide --seed or a seed value in the YAML config")
    train(raw, int(config_seed))


if __name__ == "__main__":
    main()
