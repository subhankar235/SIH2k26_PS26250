"""Tests for environment-backed application settings."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.core.config import get_settings
from backend.app.core.exceptions import ForbiddenError
from backend.app.core.security import Actor, get_actor, require_role


def test_environment_overrides_and_database_url(monkeypatch) -> None:
    """Load typed settings from environment and build the escaped DB URL."""
    monkeypatch.setenv("POSTGRES_USER", "test-user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss/word")
    monkeypatch.setenv("POSTGRES_DB", "test-db")
    monkeypatch.setenv("POSTGRES_HOST", "db.internal")
    monkeypatch.setenv("POSTGRES_PORT", "5544")
    monkeypatch.setenv("FRESHNESS_THRESHOLDS", '{"resource":120,"weather":300}')
    monkeypatch.setenv("CORS_ORIGINS", '["https://console.example"]')
    get_settings.cache_clear()
    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.postgres_port == 5544
    assert settings.freshness_thresholds == {"resource": 120, "weather": 300}
    assert settings.cors_origins == ["https://console.example"]
    assert settings.database_url == (
        "postgresql+psycopg://test-user:p%40ss%2Fword@db.internal:5544/test-db"
    )


def test_actor_authentication_and_role_dependency(monkeypatch) -> None:
    """Resolve configured API keys and reject actors lacking the required role."""
    monkeypatch.setattr(
        "backend.app.core.security.get_settings",
        lambda: SimpleNamespace(api_keys={"secret": {"id": "operator-1", "role": "analyst"}}),
    )

    actor = get_actor("secret")
    assert actor == Actor(id="operator-1", role="analyst")
    assert require_role("analyst")(actor) == actor
    with pytest.raises(ForbiddenError):
        require_role("approver")(actor)
    with pytest.raises(ForbiddenError):
        get_actor("unknown")
