"""Tests for the app health endpoint and application error responses."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.deps import get_db
from backend.app.core.exceptions import NotFoundError
from backend.app.main import create_app


def test_api_health_endpoint() -> None:
    """Return healthy status after successfully pinging the database."""
    engine = create_engine("sqlite://")
    app = create_app(get_settings())

    def test_session() -> Iterator[Session]:
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = test_session
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    engine.dispose()
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


def test_airpower_error_handler_returns_shared_error_shape() -> None:
    """Map application errors to their documented status and JSON response."""
    app = create_app(get_settings())

    def missing_decision() -> None:
        raise NotFoundError("Decision not found", {"id": "decision-1"})

    app.add_api_route("/test/not-found", missing_decision, methods=["GET"])
    with TestClient(app) as client:
        response = client.get("/test/not-found")

    assert response.status_code == 404
    assert response.json() == {
        "code": "NOT_FOUND",
        "message": "Decision not found",
        "details": {"id": "decision-1"},
    }


def test_correlation_id_is_echoed_or_generated() -> None:
    """Propagate a request id or generate one when the request has none."""
    app = create_app(get_settings())
    with TestClient(app) as client:
        supplied = client.get("/health", headers={"X-Request-ID": "request-123"})
        generated = client.get("/health")

    assert supplied.headers["X-Request-ID"] == "request-123"
    assert generated.headers["X-Request-ID"]
