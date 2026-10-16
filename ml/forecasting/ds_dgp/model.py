"""Deep Gaussian process layers and predictive inference helpers."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import NormalDist

import gpytorch
import numpy as np
import pandas as pd
import torch
from gpytorch.models.deep_gps import DeepGP, DeepGPLayer
from gpytorch.variational import CholeskyVariationalDistribution, VariationalStrategy
from torch import Tensor, nn


class _GPLayer(DeepGPLayer):
    """Independent sparse variational GP output processes for one deep layer."""

    def __init__(
        self,
        input_dims: int,
        output_dims: int | None,
        num_inducing: int,
    ) -> None:
        batch_shape = torch.Size([output_dims]) if output_dims is not None else torch.Size()
        if output_dims is None:
            inducing_points = torch.randn(num_inducing, input_dims)
        else:
            inducing_points = torch.randn(output_dims, num_inducing, input_dims)
        variational_distribution = CholeskyVariationalDistribution(
            num_inducing_points=num_inducing,
            batch_shape=batch_shape,
        )
        variational_strategy = VariationalStrategy(
            self,
            inducing_points,
            variational_distribution,
            learn_inducing_locations=True,
        )
        super().__init__(variational_strategy, input_dims=input_dims, output_dims=output_dims)
        self.mean_module = gpytorch.means.ConstantMean(batch_shape=batch_shape)
        self.covar_module = gpytorch.kernels.ScaleKernel(
            gpytorch.kernels.RBFKernel(ard_num_dims=input_dims, batch_shape=batch_shape),
            batch_shape=batch_shape,
        )

    def forward(self, inputs: Tensor) -> gpytorch.distributions.MultivariateNormal:
        """Return the variational GP distribution at the supplied layer inputs."""
        return gpytorch.distributions.MultivariateNormal(
            self.mean_module(inputs), self.covar_module(inputs)
        )


class DSDGP(DeepGP):
    """Doubly stochastic deep GP with sparse inducing-point variational layers."""

    def __init__(
        self,
        input_dims: int,
        hidden_dims: tuple[int, ...] = (16, 16),
        num_inducing: int = 64,
        *,
        x_mean: np.ndarray | list[float] | None = None,
        x_scale: np.ndarray | list[float] | None = None,
        y_mean: float = 0.0,
        y_scale: float = 1.0,
        num_likelihood_samples: int = 32,
    ) -> None:
        """Build a two- or three-GP-layer model and Gaussian observation likelihood."""
        super().__init__()
        if input_dims < 1 or num_inducing < 2:
            raise ValueError("input_dims must be positive and num_inducing must be at least 2")
        if len(hidden_dims) not in {1, 2} or any(width < 1 for width in hidden_dims):
            raise ValueError("hidden_dims must contain one or two positive layer widths")
        if num_likelihood_samples < 1:
            raise ValueError("num_likelihood_samples must be positive")
        self.input_dims = input_dims
        self.hidden_dims = tuple(int(width) for width in hidden_dims)
        self.num_inducing = num_inducing
        self.num_likelihood_samples = num_likelihood_samples
        previous_dims = input_dims
        self.hidden_layers = nn.ModuleList()
        for output_dims in self.hidden_dims:
            self.hidden_layers.append(_GPLayer(previous_dims, output_dims, num_inducing))
            previous_dims = output_dims
        self.last_layer = _GPLayer(previous_dims, None, num_inducing)
        self.likelihood = gpytorch.likelihoods.GaussianLikelihood()
        mean = (
            torch.zeros(input_dims)
            if x_mean is None
            else torch.as_tensor(x_mean, dtype=torch.float32)
        )
        scale = (
            torch.ones(input_dims)
            if x_scale is None
            else torch.as_tensor(x_scale, dtype=torch.float32)
        )
        if mean.shape != (input_dims,) or scale.shape != (input_dims,):
            raise ValueError("feature scaler arrays must match input_dims")
        if not torch.isfinite(mean).all() or not torch.isfinite(scale).all() or (scale <= 0).any():
            raise ValueError("feature scaler values must be finite and scales must be positive")
        if not np.isfinite(y_mean) or not np.isfinite(y_scale) or y_scale <= 0:
            raise ValueError("target scaler values must be finite and y_scale positive")
        self.register_buffer("x_mean", mean)
        self.register_buffer("x_scale", scale)
        self.register_buffer("y_mean", torch.tensor(float(y_mean), dtype=torch.float32))
        self.register_buffer("y_scale", torch.tensor(float(y_scale), dtype=torch.float32))
        self.feature_columns: tuple[str, ...] = tuple()
        self.training_rows = 0
        self.seed = 0

    def forward(self, inputs: Tensor) -> gpytorch.distributions.MultivariateNormal:
        """Propagate inputs through all hidden GP layers and the scalar GP output."""
        hidden = inputs
        for layer in self.hidden_layers:
            hidden = layer(hidden)
        return self.last_layer(hidden)


def load_model(path: Path) -> DSDGP:
    """Load a trained DS-DGP state and preprocessing metadata from an artifact folder."""
    artifact = Path(path)
    metadata_path = artifact / "metadata.json"
    state_path = artifact / "model.pt"
    if not metadata_path.is_file() or not state_path.is_file():
        raise FileNotFoundError(f"DS-DGP artifact is incomplete: {artifact}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or metadata.get("model") != "DSDGP":
        raise ValueError("artifact metadata does not describe a DSDGP model")
    model = DSDGP(
        input_dims=int(metadata["input_dims"]),
        hidden_dims=tuple(metadata["hidden_dims"]),
        num_inducing=int(metadata["num_inducing"]),
        x_mean=metadata["x_mean"],
        x_scale=metadata["x_scale"],
        y_mean=float(metadata["y_mean"]),
        y_scale=float(metadata["y_scale"]),
        num_likelihood_samples=int(metadata["num_likelihood_samples"]),
    )
    state = torch.load(state_path, map_location="cpu", weights_only=True)
    model.load_state_dict(state, strict=True)
    model.feature_columns = tuple(metadata["feature_columns"])
    model.training_rows = int(metadata["training_rows"])
    model.seed = int(metadata["seed"])
    model.eval()
    model.likelihood.eval()
    return model


def _feature_tensor(model: DSDGP, X: pd.DataFrame | np.ndarray) -> Tensor:
    """Validate/normalize input rows in the persisted training feature order."""
    if isinstance(X, pd.DataFrame):
        if model.feature_columns:
            missing = set(model.feature_columns) - set(X.columns)
            if missing:
                if (
                    set(model.feature_columns) == {"__time_index"}
                    and not missing - {"__time_index"}
                ):
                    values = np.arange(model.training_rows, model.training_rows + len(X))[:, None]
                else:
                    raise ValueError(f"prediction frame is missing features: {sorted(missing)}")
            else:
                values = X.loc[:, list(model.feature_columns)].to_numpy(dtype=np.float32)
        else:
            values = X.to_numpy(dtype=np.float32)
    else:
        values = np.asarray(X, dtype=np.float32)
    if values.ndim == 1:
        if model.input_dims != 1:
            raise ValueError("one-dimensional X is valid only for a single-feature model")
        values = values.reshape(-1, 1)
    if values.ndim != 2 or values.shape[1] != model.input_dims or len(values) == 0:
        raise ValueError(f"X must have shape [n, {model.input_dims}] with n > 0")
    if not np.isfinite(values).all():
        raise ValueError("prediction features must be finite")
    return (torch.tensor(values.copy()) - model.x_mean) / model.x_scale


def predict(
    model: DSDGP,
    X: pd.DataFrame | np.ndarray,
    seed: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return posterior predictive mean and 95% intervals in target units."""
    if not isinstance(model, DSDGP):
        raise TypeError("model must be a trained DSDGP")
    inputs = _feature_tensor(model, X)
    model.eval()
    model.likelihood.eval()
    active_seed = model.seed if seed is None else seed
    if not isinstance(active_seed, int) or isinstance(active_seed, bool) or active_seed < 0:
        raise ValueError("seed must be a non-negative integer")
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(active_seed)
        with torch.inference_mode(), gpytorch.settings.num_likelihood_samples(
            model.num_likelihood_samples
        ):
            predictive = model.likelihood(model(inputs))
            sample_means = predictive.mean
            sample_variances = predictive.variance
            mean = sample_means.mean(dim=0)
            variance = (sample_variances + sample_means.square()).mean(dim=0) - mean.square()
            std = variance.clamp_min(1e-10).sqrt()
    mean = mean * model.y_scale + model.y_mean
    std = std * model.y_scale
    quantile = NormalDist().inv_cdf(0.975)
    mean_np = mean.detach().cpu().numpy().reshape(-1)
    std_np = std.detach().cpu().numpy().reshape(-1)
    return mean_np, mean_np - quantile * std_np, mean_np + quantile * std_np
