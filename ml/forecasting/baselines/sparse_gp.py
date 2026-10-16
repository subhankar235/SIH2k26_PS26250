"""Sparse variational Gaussian-process autoregressive forecasting baseline."""

from __future__ import annotations

from statistics import NormalDist

import gpytorch
import numpy as np
import pandas as pd
import torch

from ml.common.seed import set_all_seeds
from ml.forecasting.baselines._common import (
    ForecastResult,
    supervised_windows,
    target_values,
)


class _SparseGP(gpytorch.models.ApproximateGP):
    """Single-output inducing-point variational GP for normalized lag windows."""

    def __init__(self, inducing_points: torch.Tensor) -> None:
        distribution = gpytorch.variational.CholeskyVariationalDistribution(
            inducing_points.size(0)
        )
        strategy = gpytorch.variational.VariationalStrategy(
            self,
            inducing_points,
            distribution,
            learn_inducing_locations=True,
        )
        super().__init__(strategy)
        self.mean_module = gpytorch.means.ConstantMean()
        self.covar_module = gpytorch.kernels.ScaleKernel(
            gpytorch.kernels.RBFKernel(ard_num_dims=inducing_points.size(-1))
        )

    def forward(self, inputs: torch.Tensor) -> gpytorch.distributions.MultivariateNormal:
        """Return the sparse GP latent distribution for lag-window rows."""
        return gpytorch.distributions.MultivariateNormal(
            self.mean_module(inputs), self.covar_module(inputs)
        )


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, seed: int) -> ForecastResult:
    """Fit a sparse variational GP and forecast recursively with 95% intervals."""
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    values, horizon = target_values(train, test)
    if len(values) < 12:
        raise ValueError("sparse GP requires at least 12 training observations")
    set_all_seeds(seed)
    torch.set_num_threads(max(1, min(torch.get_num_threads(), 2)))
    window = min(8, max(3, len(values) // 6))
    location = float(values.mean())
    scale = float(values.std())
    if scale < 1e-8:
        scale = 1.0
    normalized = (values - location) / scale
    x_np, y_np = supervised_windows(normalized, window)
    x_all = torch.from_numpy(x_np)
    y_all = torch.from_numpy(y_np)
    inducing_count = min(64, len(x_all))
    inducing_indexes = np.linspace(0, len(x_all) - 1, inducing_count, dtype=int)
    inducing = x_all[torch.as_tensor(inducing_indexes, dtype=torch.long)].clone()
    model = _SparseGP(inducing)
    likelihood = gpytorch.likelihoods.GaussianLikelihood()
    optimizer = torch.optim.Adam(
        [*model.parameters(), *likelihood.parameters()], lr=0.02
    )
    objective = gpytorch.mlls.VariationalELBO(likelihood, model, num_data=len(x_all))
    generator = torch.Generator().manual_seed(seed)
    batch_size = min(128, len(x_all))
    loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(x_all, y_all),
        batch_size=batch_size,
        shuffle=True,
        generator=generator,
    )
    epochs = 40
    for _epoch in range(epochs):
        model.train()
        likelihood.train()
        for batch_x, batch_y in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = -objective(model(batch_x), batch_y)
            if not torch.isfinite(loss):
                raise FloatingPointError("sparse GP training produced a non-finite objective")
            loss.backward()
            torch.nn.utils.clip_grad_norm_([*model.parameters(), *likelihood.parameters()], 5.0)
            optimizer.step()

    model.eval()
    likelihood.eval()
    residuals: list[float] = []
    with torch.inference_mode(), gpytorch.settings.fast_pred_var():
        for index in range(window, len(values)):
            input_row = torch.tensor(normalized[index - window : index], dtype=torch.float32)
            prediction = likelihood(model(input_row.unsqueeze(0)))
            residuals.append(float(normalized[index] - prediction.mean.item()))
        residual_scale = (
            float(np.sqrt(np.mean(np.square(residuals)))) * scale if residuals else 0.0
        )

        history = normalized.astype(np.float32).tolist()
        means: list[float] = []
        standard_deviations: list[float] = []
        for _ in range(horizon):
            input_row = torch.tensor(history[-window:], dtype=torch.float32).unsqueeze(0)
            predictive = likelihood(model(input_row))
            mean_value = float(predictive.mean.item()) * scale + location
            std_value = float(predictive.variance.clamp_min(0).sqrt().item()) * scale
            means.append(mean_value)
            standard_deviations.append(max(std_value, residual_scale))
            history.append((mean_value - location) / scale)
    steps = (
        pd.to_numeric(test["forecast_horizon_step"], errors="coerce").to_numpy(dtype=float)
        if "forecast_horizon_step" in test
        else np.arange(1, horizon + 1, dtype=float)
    )
    if not np.isfinite(steps).all() or np.any(steps < 1):
        raise ValueError("forecast_horizon_step must contain finite positive values")
    mean = np.asarray(means, dtype=np.float64)
    radius = NormalDist().inv_cdf(0.975) * np.asarray(standard_deviations) * np.sqrt(steps)
    return ForecastResult(mean, mean - radius, mean + radius)
