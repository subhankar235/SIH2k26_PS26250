"""Optional forecast creation node."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.app.agents.nodes.common import step
from backend.app.agents.state import AgentState, current_session
from backend.app.schemas.agents import EvidenceRef
from backend.app.schemas.forecast import ForecastIn
from backend.app.services.forecasting.predictor import create_forecast


def run(state: AgentState, db: Session | None = None) -> AgentState:
    """Create a requested forecast, or record an explicit skipped node step."""
    configuration: Any = state.request.request.get("forecast")
    if configuration is None:
        return state.model_copy(
            update={"steps": step(state, "prediction", "skipped", reason="no forecast requested")}
        )
    if not isinstance(configuration, dict):
        raise ValueError("agent forecast request must be an object")
    forecast_payload = {
        key: value for key, value in configuration.items() if key != "model"
    }
    request = ForecastIn.model_validate(
        {"seed": state.request.seed, **forecast_payload}
    )
    forecast = create_forecast(
        current_session(db),
        target=request.target,
        horizon=request.horizon,
        seed=request.seed,
        model=str(configuration.get("model", "ds_dgp")),
    )
    forecast_ids = list(dict.fromkeys([*state.forecast_ids, forecast.id]))
    refs = [
        *state.evidence_refs,
        EvidenceRef(kind="forecast", id=forecast.id, version=forecast.version),
    ]
    next_request = state.request.model_copy(deep=True)
    request_payload = dict(next_request.request)
    solve_payload = request_payload.get("solve")
    if isinstance(solve_payload, dict):
        solve_payload = dict(solve_payload)
        problem_payload = solve_payload.get("problem")
        if isinstance(problem_payload, dict):
            solve_payload["problem"] = {**problem_payload, "forecast_id": str(forecast.id)}
        request_payload["solve"] = solve_payload
    else:
        problem_payload = request_payload.get("problem")
        if isinstance(problem_payload, dict):
            request_payload["problem"] = {**problem_payload, "forecast_id": str(forecast.id)}
    next_request.request = request_payload
    return state.model_copy(
        update={
            "request": next_request,
            "forecast_ids": forecast_ids,
            "evidence_refs": list({(ref.kind, ref.id, ref.version): ref for ref in refs}.values()),
            "steps": step(
                state,
                "prediction",
                "completed",
                forecast_id=str(forecast.id),
                version=forecast.version,
                high_uncertainty=forecast.high_uncertainty,
            ),
        }
    )
