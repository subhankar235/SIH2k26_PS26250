"""Tests for route registration, role gates, and routed service responses."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

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
from backend.app.main import create_app

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
            yield db

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
