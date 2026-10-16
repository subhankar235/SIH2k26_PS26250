"""Seeded autoregressive LSTM baseline with held-out residual intervals."""

from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd
import torch
from torch import nn

from ml.common.seed import set_all_seeds
from ml.forecasting.baselines._common import (
    ForecastResult,
    supervised_windows,
    target_values,
)


class _LSTMRegressor(nn.Module):
    """Small one-layer sequence-to-one LSTM regressor."""

    def __init__(self, hidden_size: int) -> None:
        super().__init__()
        self.recurrent = nn.LSTM(input_size=1, hidden_size=hidden_size, batch_first=True)
        self.output = nn.Linear(hidden_size, 1)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        sequence, _state = self.recurrent(inputs.unsqueeze(-1))
        return self.output(sequence[:, -1]).squeeze(-1)


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, seed: int) -> ForecastResult:
    """Fit a real LSTM on rolling target windows and predict recursively.

    A trailing chronological holdout estimates one-step residual scale. Training
    uses only observations before that holdout; later test horizons are recursive,
    so no test targets or future actual lag values are consumed.
    """
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    values, horizon = target_values(train, test)
    if len(values) < 12:
        raise ValueError("LSTM requires at least 12 training observations")
    set_all_seeds(seed)
    window = min(12, max(3, len(values) // 5))
    split = min(len(values) - 1, max(window + 3, int(len(values) * 0.8)))
    if split >= len(values):
        split = len(values) - 1
    train_values = values[:split]
    location = float(train_values.mean())
    scale = float(train_values.std())
    if scale < 1e-8:
        scale = 1.0
    standardized = (train_values - location) / scale
    x_train, y_train = supervised_windows(standardized, window)
    x_tensor = torch.from_numpy(x_train)
    y_tensor = torch.from_numpy(y_train)
    model = _LSTMRegressor(hidden_size=16)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    epochs = 60
    batch_size = min(64, len(x_tensor))
    generator = torch.Generator().manual_seed(seed)
    loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(x_tensor, y_tensor),
        batch_size=batch_size,
        shuffle=True,
        generator=generator,
    )
    for _epoch in range(epochs):
        model.train()
        for batch_x, batch_y in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = nn.functional.mse_loss(model(batch_x), batch_y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

    model.eval()
    residuals: list[float] = []
    with torch.inference_mode():
        history = values[:split].astype(np.float32).tolist()
        for actual in values[split:]:
            recent = np.asarray(history[-window:], dtype=np.float32)
            normalized = torch.from_numpy((recent - location) / scale).unsqueeze(0)
            prediction = float(model(normalized).item()) * scale + location
            residuals.append(float(actual - prediction))
            history.append(float(actual))
    residual_scale = float(np.sqrt(np.mean(np.square(residuals)))) if residuals else 0.0

    forecast_history = ((values - location) / scale).astype(np.float32).tolist()
    means: list[float] = []
    with torch.inference_mode():
        for _ in range(horizon):
            sequence = torch.tensor(forecast_history[-window:], dtype=torch.float32).unsqueeze(0)
            prediction = float(model(sequence).item()) * scale + location
            means.append(prediction)
            forecast_history.append((prediction - location) / scale)
    horizon_steps = (
        pd.to_numeric(test["forecast_horizon_step"], errors="coerce").to_numpy(dtype=float)
        if "forecast_horizon_step" in test
        else np.arange(1, horizon + 1, dtype=float)
    )
    if not np.isfinite(horizon_steps).all() or np.any(horizon_steps < 1):
        raise ValueError("forecast_horizon_step must contain finite positive values")
    standard_deviations = residual_scale * np.sqrt(horizon_steps)
    radius = NormalDist().inv_cdf(0.975) * standard_deviations
    mean = np.asarray(means, dtype=np.float64)
    return ForecastResult(mean, mean - radius, mean + radius)
