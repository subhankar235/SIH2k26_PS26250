"""Smoke tests for the public API."""

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_grid_summary_shape() -> None:
    response = client.get("/api/v1/grid/summary")
    assert response.status_code == 200
    assert response.json()["total_assets"] >= response.json()["healthy_assets"]
