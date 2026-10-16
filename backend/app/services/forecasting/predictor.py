"""Create persisted forecasts with configured model fallback."""

from __future__ import annotations

import importlib
import inspect
import os
from datetime import datetime, timedelta
from math import ceil
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.exceptions import (
    ConflictError,
    ForecastModelUnavailableError,
    NotFoundError,
    RequestValidationFailed,
)
from backend.app.db.models.forecast import Forecast
from backend.app.db.models.record import Record
from backend.app.schemas.forecast import ForecastPoint
from backend.app.services.audit.audit_service import record as audit_record
from backend.app.services.forecasting.features import build_features
from backend.app.services.ingestion.normaliser import to_utc


class ForecastModel(Protocol):
    """Protocol for a model returning point means and prediction bounds."""

    def predict(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Predict mean, lower, and upper values for feature rows."""
        ...


def _validate_prediction_outputs(
    outputs: tuple[Any, Any, Any],
    expected_length: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Validate one-dimensional predictive arrays and ordered finite intervals."""
    arrays = tuple(np.asarray(output, dtype=float) for output in outputs)
    if any(array.ndim != 1 for array in arrays):
        raise ForecastModelUnavailableError("Forecast model outputs must be one-dimensional")
    if any(len(array) != expected_length for array in arrays):
        raise ForecastModelUnavailableError("Forecast model returned the wrong output length")
    means, lowers, uppers = arrays
    if (
        not np.isfinite(means).all()
        or not np.isfinite(lowers).all()
        or not np.isfinite(uppers).all()
    ):
        raise ForecastModelUnavailableError("Forecast model returned non-finite values")
    if np.any(lowers > means) or np.any(means > uppers):
        raise ForecastModelUnavailableError("Forecast intervals must contain their means")
    return means, lowers, uppers


class _ExternalForecastModel:
    """Adapt a loaded ML module's ``predict(model, X)`` callable."""

    def __init__(self, module: Any, model: Any) -> None:
        self._module = module
        self._model = model
        self._seed = 0

    def set_seed(self, seed: int) -> None:
        """Pass a local seed to model implementations that expose a seed setter."""
        self._seed = seed
        setter = getattr(self._model, "set_seed", None) or getattr(
            self._model, "set_random_seed", None
        )
        if callable(setter):
            setter(seed)

    def predict(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Call the loaded model and normalize outputs to NumPy arrays."""
        prediction = self._module.predict
        try:
            supports_seed = "seed" in inspect.signature(prediction).parameters
        except (TypeError, ValueError):
            supports_seed = False
        result = (
            prediction(self._model, X, seed=self._seed)
            if supports_seed
            else prediction(self._model, X)
        )
        if not isinstance(result, tuple) or len(result) != 3:
            raise ForecastModelUnavailableError("Forecast model must return mean/lower/upper")
        return _validate_prediction_outputs(result, len(X))


class _FitPredictAdapter:
    """Adapt a baseline module's ``fit_predict(train, test, seed)`` contract."""

    def __init__(self, fit_predict: Any) -> None:
        self._fit_predict = fit_predict
        self._train = pd.DataFrame()
        self._seed = 0

    def clone(self) -> _FitPredictAdapter:
        """Return an unfit adapter around the same pure model function."""
        return _FitPredictAdapter(self._fit_predict)

    def fit(self, values: list[float], seed: int) -> None:
        """Store past-only training values and a deterministic model seed.

        Args:
            values: Historical numeric target observations.
            seed: Local model seed used by the baseline implementation.

        Returns:
            None.
        """
        self._train = pd.DataFrame({"target": np.asarray(values, dtype=float)})
        self._seed = seed

    def predict(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Run the baseline estimator and adapt its ForecastResult or tuple output."""
        result = self._fit_predict(self._train, X, seed=self._seed)
        if isinstance(result, tuple) and len(result) == 3:
            outputs = result
        else:
            outputs = (result.mean, result.lower, result.upper)
        return _validate_prediction_outputs(outputs, len(X))


def load_model(name: str) -> ForecastModel:
    """Load an optional trained model or an implemented statistical baseline.

    Args:
        name: Model in the fallback order ``ds_dgp``, ``sparse_gp``, ``arima``.

    Returns:
        A model implementing ``predict(X) -> (mean, lower, upper)``.

    Raises:
        ForecastModelUnavailableError: If the named model is not installed/configured.
    """
    module_names = {
        "ds_dgp": "ml.forecasting.ds_dgp.model",
        "sparse_gp": "ml.forecasting.baselines.sparse_gp",
        "arima": "ml.forecasting.baselines.arima",
    }
    module_name = module_names.get(name)
    if module_name is None:
        raise ForecastModelUnavailableError(f"Unknown forecast model {name!r}")
    try:
        module = importlib.import_module(module_name)
    except Exception as error:
        raise ForecastModelUnavailableError(
            f"Model {name!r} module could not be loaded",
            {"module": module_name, "error_type": type(error).__name__, "error": str(error)},
        ) from error

    fit_predict = getattr(module, "fit_predict", None)
    if callable(fit_predict) and name in {"sparse_gp", "arima"}:
        return _FitPredictAdapter(fit_predict)

    if name == "arima":
        raise ForecastModelUnavailableError("ARIMA baseline does not expose fit_predict")
    model_path = os.getenv(f"{name.upper()}_MODEL_PATH")
    try:
        loader = getattr(module, "load_model", None) or getattr(module, "load", None)
        predict = getattr(module, "predict", None)
        if not callable(loader) or not callable(predict) or not model_path:
            raise ForecastModelUnavailableError(
                f"Model {name!r} is not trained or its model path is not configured"
            )
        model = loader(Path(model_path))
    except ForecastModelUnavailableError:
        raise
    except Exception as error:
        raise ForecastModelUnavailableError(
            f"Model {name!r} could not be initialized",
            {"module": module_name, "error_type": type(error).__name__, "error": str(error)},
        ) from error
    return _ExternalForecastModel(module, model)


def _target_parts(target: str) -> tuple[str | None, str]:
    """Split an optional entity-qualified target into entity and field."""
    if "." not in target:
        return None, target
    entity_id, field = target.rsplit(".", 1)
    if not entity_id or not field:
        raise RequestValidationFailed("Forecast target must be an attribute or entity.attribute")
    return entity_id, field


def _future_features(
    history: list[float],
    history_timestamps: list[datetime],
    target: str,
    timestamp: datetime,
) -> pd.DataFrame:
    """Create one no-leakage feature row for a future timestamp."""
    index = pd.DatetimeIndex([*history_timestamps, timestamp])
    # The placeholder at timestamp is shifted out by build_features; it cannot leak.
    frame = pd.DataFrame({target: [*history, history[-1]]}, index=index)
    return build_features(frame, target, [1, 2, 3], [3, 6]).iloc[[-1]].copy()


def _history(
    db: Session,
    target: str,
) -> tuple[str, list[datetime], list[float], dict[str, int]]:
    """Extract time-ordered numeric target observations and their versions."""
    entity_filter, field = _target_parts(target)
    records = db.scalars(
        select(Record).where(Record.superseded_by.is_(None)).order_by(Record.event_time, Record.id)
    ).all()
    selected = [
        record
        for record in records
        if (entity_filter is None or record.entity_id == entity_filter)
        and field in record.normalised_payload
    ]
    entity_ids = {record.entity_id for record in selected}
    if entity_filter is None and len(entity_ids) > 1:
        raise RequestValidationFailed(
            "Forecast target matches multiple entities; qualify it as entity_id.field",
            {"target": target, "entity_count": len(entity_ids)},
        )
    pairs: list[tuple[datetime, float, Record]] = []
    for record in selected:
        try:
            value = float(record.normalised_payload[field])
        except (TypeError, ValueError) as error:
            raise RequestValidationFailed(
                "Forecast target contains a non-numeric observation",
                {"target": target, "record_id": str(record.id)},
            ) from error
        if not np.isfinite(value):
            raise RequestValidationFailed(
                "Forecast target contains a non-finite observation",
                {"target": target, "record_id": str(record.id)},
            )
        pairs.append((to_utc(record.event_time), value, record))
    pairs.sort(key=lambda item: (item[0], str(item[2].id)))
    if not pairs:
        raise NotFoundError("No numeric observations found for forecast target", {"target": target})
    values_by_time: dict[datetime, set[float]] = {}
    for timestamp, value, _ in pairs:
        values_by_time.setdefault(timestamp, set()).add(value)
    conflicting_times = [
        timestamp for timestamp, values in values_by_time.items() if len(values) > 1
    ]
    if conflicting_times:
        raise ConflictError(
            "Forecast target has conflicting values at the same event time",
            {"target": target, "event_time": min(conflicting_times).isoformat()},
        )
    input_versions = {str(record.id): record.version for _, _, record in pairs}
    time_groups: dict[datetime, float] = {}
    for timestamp, value, _ in pairs:
        time_groups.setdefault(timestamp, value)
    ordered_times = sorted(time_groups)
    return (
        field,
        ordered_times,
        [time_groups[timestamp] for timestamp in ordered_times],
        input_versions,
    )


def _forecast_points(
    model: ForecastModel,
    target: str,
    history_timestamps: list[datetime],
    future_timestamps: list[datetime],
    history: list[float],
    calibration_radius: float | None,
) -> list[ForecastPoint]:
    """Recursively generate forecast points without reading future targets."""
    values = list(history)
    value_times = list(history_timestamps)
    points: list[ForecastPoint] = []
    for step, timestamp in enumerate(future_timestamps, start=1):
        features = _future_features(values, value_times, target, timestamp)
        features["forecast_horizon_step"] = float(step)
        means, lowers, uppers = _validate_prediction_outputs(model.predict(features), 1)
        mean, lower, upper = float(means[0]), float(lowers[0]), float(uppers[0])
        if calibration_radius is not None:
            conformal_radius = calibration_radius * float(np.sqrt(step))
            lower = min(lower, mean - conformal_radius)
            upper = max(upper, mean + conformal_radius)
        points.append(ForecastPoint(t=timestamp, mean=mean, lower=lower, upper=upper))
        values.append(mean)
        value_times.append(timestamp)
    return points


def _calibration_radius(
    model: ForecastModel,
    target: str,
    timestamps: list[datetime],
    values: list[float],
    seed: int,
    coverage_level: float = 0.9,
) -> float | None:
    """Compute a finite-sample, past-only conformal residual radius.

    Args:
        model: Candidate model used for rolling-origin predictions.
        target: Numeric target field.
        timestamps: Chronological observation times.
        values: Observed target values aligned with timestamps.
        seed: Reproducibility seed for fold-specific fitted models.
        coverage_level: Desired marginal interval coverage in (0, 1).

    Returns:
        Empirical absolute-residual quantile, or None when history is insufficient.
    """
    if not 0 < coverage_level < 1:
        raise ValueError("coverage_level must be in (0, 1)")
    clone = getattr(model, "clone", None)
    if not callable(clone) or not callable(getattr(model, "fit", None)):
        # A pre-trained external model cannot be safely calibrated on the same
        # history without a held-out calibration set.
        return None
    residuals: list[float] = []
    for index in range(2, len(values)):
        features = _future_features(values[:index], timestamps[:index], target, timestamps[index])
        fold_model = clone()
        fitter = getattr(fold_model, "fit", None)
        if callable(fitter):
            fitter(values[:index], seed=seed)
        features["forecast_horizon_step"] = 1.0
        means, _, _ = _validate_prediction_outputs(fold_model.predict(features), 1)
        residuals.append(abs(values[index] - float(means[0])))
    if not residuals:
        return None
    ordered = np.sort(np.asarray(residuals, dtype=float))
    rank = min(len(ordered), ceil((len(ordered) + 1) * coverage_level))
    return float(ordered[rank - 1])


def create_forecast(
    db: Session,
    target: str,
    horizon: int,
    seed: int,
    model: str = "ds_dgp",
) -> Forecast:
    """Create and audit a versioned forecast using the documented model fallback chain.

    Args:
        db: Active synchronous database session.
        target: Numeric payload field or entity-qualified ``entity_id.field``.
        horizon: Number of future points to produce.
        seed: Seed included for reproducible model implementations and metadata.
        model: Preferred model name; subsequent fallback models are tried on failure.

    Returns:
        Persisted forecast with point intervals and input record versions.

    Raises:
        RequestValidationFailed: If horizon or target is invalid.
        NotFoundError: If no numeric observations exist for the target.
        ServiceUnavailableError: If all fallback models are unavailable.
        SQLAlchemyError: If the forecast or audit entry cannot be persisted.
    """
    if not isinstance(target, str) or not target.strip():
        raise RequestValidationFailed("Forecast target must be a non-empty string")
    if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon < 1:
        raise RequestValidationFailed("Forecast horizon must be positive")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise RequestValidationFailed("Forecast seed must be an integer")
    fallback_chain = ("ds_dgp", "sparse_gp", "arima")
    if model not in fallback_chain:
        raise RequestValidationFailed(
            "Unknown preferred forecast model",
            {"model": model, "supported_models": list(fallback_chain)},
        )
    field, timestamps, history, input_versions = _history(db, target)
    if len(history) < 3:
        raise RequestValidationFailed(
            "At least three historical observations are required for forecasting",
            {"target": target, "observations": len(history), "minimum": 3},
        )
    if len(timestamps) >= 2:
        deltas = [
            (right - left).total_seconds()
            for left, right in zip(timestamps, timestamps[1:], strict=False)
            if right > left
        ]
        cadence_seconds = float(np.median(deltas)) if deltas else 3600.0
    else:
        cadence_seconds = 3600.0
    cadence_seconds = max(1.0, cadence_seconds)
    future_times = [
        timestamps[-1] + timedelta(seconds=cadence_seconds * step) for step in range(1, horizon + 1)
    ]

    preferred = list(fallback_chain[fallback_chain.index(model) :])
    selected_model: ForecastModel | None = None
    selected_name = ""
    points: list[ForecastPoint] | None = None
    selected_calibration_radius: float | None = None
    fallback_reasons: list[str] = []
    for model_name in preferred:
        try:
            candidate = load_model(model_name)
            seed_setter = getattr(candidate, "set_seed", None)
            if callable(seed_setter):
                seed_setter(seed)
            fitter = getattr(candidate, "fit", None)
            if callable(fitter):
                fitter(history, seed=seed)
            calibration_radius = _calibration_radius(
                candidate,
                field,
                timestamps,
                history,
                seed,
            )
            candidate_points = _forecast_points(
                candidate,
                field,
                timestamps,
                future_times,
                history,
                calibration_radius,
            )
        except ForecastModelUnavailableError as error:
            context = f"; context={error.details!r}" if error.details else ""
            fallback_reasons.append(f"{model_name}: {error.message}{context}")
            continue
        except ValueError as error:
            fallback_reasons.append(f"{model_name}: {error}")
            continue
        except Exception as error:
            fallback_reasons.append(f"{model_name}: {type(error).__name__}: {error}")
            continue
        selected_model = candidate
        selected_name = model_name
        points = candidate_points
        selected_calibration_radius = calibration_radius
        break
    if selected_model is None or points is None:
        raise ForecastModelUnavailableError(
            "All permitted forecasting models failed",
            {"requested_model": model, "attempts": fallback_reasons},
        )

    previous_version = db.scalar(
        select(Forecast.version)
        .where(Forecast.target == target)
        .order_by(Forecast.version.desc())
        .limit(1)
    )
    version = (previous_version or 0) + 1
    uncertainty_threshold = get_settings().uncertainty_threshold
    target_scale = max(float(np.std(history)), abs(float(np.mean(history))))
    relative_widths = [
        (
            (point.upper - point.lower) / target_scale
            if target_scale > 0
            else (0.0 if point.upper == point.lower else float("inf"))
        )
        for point in points
    ]
    high_uncertainty = any(width > uncertainty_threshold for width in relative_widths)
    forecast = Forecast(
        target=target,
        horizon=horizon,
        points=[point.model_dump(mode="json") for point in points],
        calibration_meta={
            "selected_model": selected_name,
            "requested_model": model,
            "fallback_reasons": fallback_reasons,
            "seed": seed,
            "training_observations": len(history),
            "cadence_seconds": cadence_seconds,
            "target_field": field,
            "target_scale": target_scale,
            "calibration_method": (
                "rolling_origin_conformal_90"
                if selected_calibration_radius is not None
                else "model_interval"
            ),
            "calibration_radius": selected_calibration_radius,
            "calibration_samples": max(0, len(history) - 2),
        },
        input_versions=input_versions,
        version=version,
        high_uncertainty=high_uncertainty,
    )
    db.add(forecast)
    db.flush()
    audit_record(
        db,
        "forecast",
        forecast.id,
        "created",
        None,
        {"target": target, "version": version, "model": selected_name},
        "forecasting",
    )
    return forecast


def get(db: Session, forecast_id: UUID) -> Forecast:
    """Load one persisted forecast.

    Args:
        db: Active synchronous database session.
        forecast_id: UUID of the requested forecast.

    Returns:
        The forecast ORM object.

    Raises:
        NotFoundError: If the forecast does not exist.
    """
    forecast = db.get(Forecast, forecast_id)
    if forecast is None:
        raise NotFoundError("Forecast not found", {"id": str(forecast_id)})
    return forecast
