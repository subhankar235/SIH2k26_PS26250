"""Tests for route registration, role gates, and routed service responses."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.core import security
from backend.app.core.config import get_settings
from backend.app.core.deps import get_db
from backend.app.db import models as _models  # noqa: F401
from backend.app.db.base import Base
from backend.app.db.models import Forecast, IdempotencyRecord, RawEvent, Record, Source
from backend.app.main import create_app
from backend.app.schemas.validity import AssumptionIn, InputRef
from backend.app.services.validity.assumption_tracker import register_decision

EXPECTED_ROUTES = {
    "/api/v1/health": {"GET"},
    "/api/v1/ingestion/events": {"POST"},
    "/api/v1/ingestion/status": {"GET"},
    "/api/v1/ingestion/flagged": {"GET"},
    "/api/v1/evidence/issues": {"GET"},
    "/api/v1/evidence/issues/{id}/autopsy": {"GET"},
    "/api/v1/evidence/provenance/{record_id}": {"GET"},
    "/api/v1/validity/decisions": {"GET"},
    "/api/v1/validity/decisions/{id}": {"GET"},
    "/api/v1/validity/reverify": {"POST"},
    "/api/v1/forecasts": {"POST"},
    "/api/v1/forecasts/{id}": {"GET"},
    "/api/v1/planning/solve": {"POST"},
    "/api/v1/planning/schedules/{id}": {"GET"},
    "/api/v1/planning/alternatives": {"GET"},
    "/api/v1/replanning/run": {"POST"},
    "/api/v1/replanning/diff/{old}/{new}": {"GET"},
    "/api/v1/stress/runs": {"POST"},
    "/api/v1/stress/runs/{id}": {"GET"},
    "/api/v1/agents/requests": {"POST"},
    "/api/v1/agents/requests/{id}": {"GET"},
    "/api/v1/agents/requests/{id}/explanation": {"GET"},
    "/api/v1/verification/check": {"POST"},
    "/api/v1/verification/{id}": {"GET"},
    "/api/v1/approvals": {"GET"},
    "/api/v1/approvals/{id}/decision": {"POST"},
    "/api/v1/audit": {"GET"},
    "/api/v1/audit/{entity}/{id}": {"GET"},
    "/api/v1/benchmarks/results": {"GET"},
    "/api/v1/benchmarks/ablations": {"GET"},
}


def test_documented_routes_and_status_codes_are_registered() -> None:
    """Register each documented endpoint with the required HTTP methods."""
    app = create_app(get_settings())
    routes = {
        route.path: route
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/")
    }

    assert set(routes) >= set(EXPECTED_ROUTES)
    for path, methods in EXPECTED_ROUTES.items():
        assert methods <= routes[path].methods

    assert routes["/api/v1/stress/runs"].status_code == 202
    assert routes["/api/v1/agents/requests"].status_code == 202
    assert all(method == "GET" for method in routes["/api/v1/audit"].methods)
    assert all(method == "GET" for method in routes["/api/v1/audit/{entity}/{id}"].methods)


def _test_database_override(app: FastAPI) -> None:
    """Install an in-memory session dependency for API contract tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def session_override() -> Iterator[Session]:
        with Session(engine) as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = session_override
    app.state.test_engine = engine


def test_role_protected_route_denies_bad_keys_and_dispatches_for_allowed_actor(
    monkeypatch,
) -> None:
    """Return 403 for an invalid credential and a service response for a valid actor."""
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(api_keys={"analyst-key": {"id": "analyst-1", "role": "analyst"}}),
    )
    app = create_app(get_settings())
    _test_database_override(app)
    with TestClient(app) as client:
        denied = client.get("/api/v1/ingestion/status", headers={"X-API-Key": "invalid"})
        accepted = client.get("/api/v1/ingestion/status", headers={"X-API-Key": "analyst-key"})
    app.state.test_engine.dispose()

    assert denied.status_code == 403
    assert denied.json()["code"] == "FORBIDDEN"
    assert accepted.status_code == 200
    assert len(accepted.json()["topics"]) == 5


def test_approval_queue_requires_approver_role(monkeypatch) -> None:
    """Prevent a viewer from entering the approver-only queue."""
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(api_keys={"viewer-key": {"id": "viewer-1", "role": "viewer"}}),
    )
    app = create_app(get_settings())
    _test_database_override(app)
    with TestClient(app) as client:
        response = client.get("/api/v1/approvals", headers={"X-API-Key": "viewer-key"})
    app.state.test_engine.dispose()

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_forecast_api_is_seeded_versioned_and_idempotent(monkeypatch) -> None:
    """Create one forecast through the API and replay without duplicate work."""
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(api_keys={"analyst-key": {"id": "analyst-1", "role": "analyst"}}),
    )
    app = create_app(get_settings())
    _test_database_override(app)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(app.state.test_engine) as db:
        source = Source(name="forecast-api-source", source_type="resource", reliability_prior=0.8)
        db.add(source)
        db.flush()
        for index_value, value in enumerate((1.0, 2.0, 3.0, 4.0)):
            timestamp = start + timedelta(hours=index_value)
            raw_event = RawEvent(
                source_id=source.id,
                source_event_id=f"forecast-api-{index_value}",
                payload={"entity_id": "resource:api", "load_mw": value},
                event_time=timestamp,
                ingest_time=timestamp,
            )
            db.add(raw_event)
            db.flush()
            db.add(
                Record(
                    entity_id="resource:api",
                    source_type="resource",
                    normalised_payload={"entity_id": "resource:api", "load_mw": value},
                    source_id=source.id,
                    raw_event_id=raw_event.id,
                    event_time=timestamp,
                    ingest_time=timestamp,
                    version=index_value + 1,
                )
            )
        db.commit()

    body = {"target": "resource:api.load_mw", "horizon": 2, "seed": 42}
    with TestClient(app) as client:
        headers = {"X-API-Key": "analyst-key", "Idempotency-Key": "forecast-create-1"}
        first = client.post("/api/v1/forecasts", json=body, headers=headers)
        replay = client.post("/api/v1/forecasts", json=body, headers=headers)

    assert first.status_code == replay.status_code == 200
    assert first.json()["id"] == replay.json()["id"]
    assert first.json()["version"] == 1
    with Session(app.state.test_engine) as db:
        assert len(db.query(Forecast).all()) == 1
        assert len(db.query(IdempotencyRecord).all()) == 1
    app.state.test_engine.dispose()


def test_validity_reverify_api_marks_dependent_decision_stale(monkeypatch) -> None:
    """Run incremental validity processing through the authenticated API."""
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(api_keys={"analyst-key": {"id": "analyst-1", "role": "analyst"}}),
    )
    app = create_app(get_settings())
    _test_database_override(app)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(app.state.test_engine) as db:
        source = Source(name="validity-api-source", source_type="resource", reliability_prior=0.8)
        db.add(source)
        db.flush()
        raw = RawEvent(
            source_id=source.id,
            source_event_id="validity-api-event",
            payload={"entity_id": "resource:decision", "value": 1},
            event_time=timestamp,
            ingest_time=timestamp,
        )
        db.add(raw)
        db.flush()
        record = Record(
            entity_id="resource:decision",
            source_type="resource",
            normalised_payload={"entity_id": "resource:decision", "value": 1},
            source_id=source.id,
            raw_event_id=raw.id,
            event_time=timestamp,
            ingest_time=timestamp,
        )
        db.add(record)
        db.flush()
        decision = register_decision(
            db,
            "schedule",
            uuid4(),
            [InputRef(input_type="record", input_id=record.id, input_version=1)],
            [AssumptionIn(description="resource remains available")],
        )
        decision_id = decision.id
        record_id = record.id
        record.version = 2
        record.ingest_time = timestamp + timedelta(days=1)
        db.commit()

    with TestClient(app) as client:
        listing = client.get("/api/v1/validity/decisions", headers={"X-API-Key": "analyst-key"})
        decision_response = client.get(
            f"/api/v1/validity/decisions/{decision_id}",
            headers={"X-API-Key": "analyst-key"},
        )
        response = client.post(
            "/api/v1/validity/reverify",
            headers={"X-API-Key": "analyst-key"},
            json={
                "change_events": [
                    {
                        "input_type": "record",
                        "input_id": str(record_id),
                        "old_version": 1,
                        "new_version": 2,
                        "changed_at": "2026-01-02T00:00:00Z",
                    }
                ]
            },
        )

    assert listing.status_code == decision_response.status_code == 200
    assert listing.json()["items"][0]["id"] == str(decision_id)
    assert decision_response.json()["type"] == "schedule"
    assert response.status_code == 200
    assert response.json()["affected"] == [str(decision_id)]
    assert response.json()["status_changes"][0]["new_status"] == "stale"
    app.state.test_engine.dispose()
