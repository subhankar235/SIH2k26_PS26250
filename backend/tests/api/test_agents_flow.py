"""API integration coverage for the asynchronous agent workflow service."""

from __future__ import annotations

import time
from collections.abc import Iterator
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core import security
from backend.app.core.config import get_settings
from backend.app.core.deps import get_db
from backend.app.db import models as _models  # noqa: F401
from backend.app.db.base import Base
from backend.app.main import create_app


def test_agent_api_runs_graph_and_returns_validated_explanation(monkeypatch, tmp_path) -> None:
    """Start a 202 workflow, poll its graph state, and fetch its grounded explanation."""
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            api_keys={
                "agent-analyst": {"id": "agent-planner", "role": "analyst"},
                "agent-viewer": {"id": "agent-reader", "role": "viewer"},
            }
        ),
    )
    app: FastAPI = create_app(get_settings())
    engine = create_engine(
        f"sqlite:///{tmp_path / 'agent-workflow.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)

    def session_override() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = session_override
    with TestClient(app) as client:
        started = client.post(
            "/api/v1/agents/requests",
            json={
                "seed": 11,
                "request": {
                    "problem": {
                        "tasks": [
                            {
                                "id": "api-task",
                                "duration": 1,
                                "resource_type": "crew",
                                "earliest": 0,
                                "latest": 3,
                            }
                        ],
                        "resources": [
                            {
                                "id": "api-crew",
                                "type": "crew",
                                "capacity": 1,
                                "available": [[0, 5]],
                            }
                        ],
                        "windows": {"horizon": 5},
                        "precedence": [],
                        "policies": [],
                        "objectives": {"makespan": 1.0},
                    },
                    "time_limit_s": 2,
                },
            },
            headers={"X-API-Key": "agent-analyst"},
        )
        assert started.status_code == 202, started.text
        run_id = started.json()["id"]
        assert started.json()["status"] == "pending"

        current = started
        for _attempt in range(100):
            current = client.get(
                f"/api/v1/agents/requests/{run_id}",
                headers={"X-API-Key": "agent-viewer"},
            )
            assert current.status_code == 200, current.text
            if current.json()["status"] == "awaiting_approval":
                break
            time.sleep(0.05)
        assert current.json()["status"] == "awaiting_approval"
        assert {step["name"] for step in current.json()["steps"]} >= {
            "evidence",
            "prediction",
            "change_analysis",
            "optimise",
            "verify",
            "explain",
        }
        explanation = client.get(
            f"/api/v1/agents/requests/{run_id}/explanation",
            headers={"X-API-Key": "agent-viewer"},
        )

    assert explanation.status_code == 200, explanation.text
    assert explanation.json()["evidence_refs"]
    assert "verification outcome is verified" in explanation.json()["text"]
    engine.dispose()
