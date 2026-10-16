"""End-to-end API tests for CP-SAT planning and independent verification."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.core import security
from backend.app.core.config import get_settings
from backend.app.core.deps import get_db
from backend.app.db import models as _models  # noqa: F401
from backend.app.db.base import Base
from backend.app.db.models import AuditEntry, Decision, Schedule, VerificationResult
from backend.app.main import create_app
from backend.app.services.verification.constraint_checker import (
    ProblemData,
    ScheduleData,
    check_all,
)


def _client_app(monkeypatch) -> FastAPI:
    """Create an app with an isolated in-memory database and analyst key."""
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            api_keys={"planning-analyst": {"id": "planner-1", "role": "analyst"}}
        ),
    )
    app = create_app(get_settings())
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
    return app


def _request(resource_type: str = "crew", use_alns: bool = False) -> dict[str, object]:
    """Return a two-task problem with a precedence and resource window."""
    return {
        "problem": {
            "tasks": [
                {
                    "id": "repair-a",
                    "duration": 2,
                    "resource_type": resource_type,
                    "earliest": 0,
                    "latest": 8,
                },
                {
                    "id": "repair-b",
                    "duration": 1,
                    "resource_type": resource_type,
                    "earliest": 0,
                    "latest": 8,
                },
            ],
            "resources": [
                {
                    "id": "crew-1",
                    "type": "crew",
                    "capacity": 1,
                    "available": [[0, 10]],
                    "cost_per_unit": 1.0,
                }
            ],
            "windows": {"horizon": 10},
            "precedence": [{"before": "repair-a", "after": "repair-b", "min_gap": 0}],
            "policies": [],
            "objectives": {"makespan": 1.0, "cost": 0.1},
        },
        "use_alns": use_alns,
        "time_limit_s": 2,
        "seed": 19,
    }


def test_planning_api_solves_verifies_registers_decision_and_replays_idempotently(
    monkeypatch,
) -> None:
    """Solve, independently recheck, audit, register validity, and cache replay."""
    app = _client_app(monkeypatch)
    request = _request(use_alns=True)
    headers = {"X-API-Key": "planning-analyst", "Idempotency-Key": "solve-repair-a"}
    with TestClient(app) as client:
        first = client.post("/api/v1/planning/solve", json=request, headers=headers)
        replay = client.post("/api/v1/planning/solve", json=request, headers=headers)

    assert first.status_code == replay.status_code == 200, first.text
    payload = first.json()
    assert payload["id"] == replay.json()["id"]
    assert payload["status"] == "verified"
    assert payload["version"] == 2
    assert len(payload["assignments"]) == 2
    assert next(
        item for item in payload["assignments"] if item["task_id"] == "repair-a"
    )["end"] <= next(
        item for item in payload["assignments"] if item["task_id"] == "repair-b"
    )["start"]

    with Session(app.state.test_engine) as db:
        schedule = db.get(Schedule, UUID(payload["id"]))
        assert schedule is not None
        problem_data = schedule.solver_meta["problem"]
        violations = check_all(
            ScheduleData(schedule.assignments),
            ProblemData(
                tasks=problem_data["tasks"],
                resources=problem_data["resources"],
                precedence=problem_data["precedence"],
                policies=problem_data["policies"],
                horizon=problem_data["horizon"],
            ),
        )
        assert violations == []
        assert len(db.scalars(select(Schedule)).all()) == 1
        assert len(db.scalars(select(VerificationResult)).all()) == 1
        assert len(db.scalars(select(Decision)).all()) == 1
        schedule_audits = db.scalars(
            select(AuditEntry).where(
                AuditEntry.entity_type == "schedule",
                AuditEntry.entity_id == schedule.id,
            )
        ).all()
        assert {entry.action for entry in schedule_audits} >= {
            "created",
            "verification_status_changed",
        }
    app.state.test_engine.dispose()


def test_planning_api_maps_cp_sat_infeasibility_to_solver_error(monkeypatch) -> None:
    """Return a reasoned INFEASIBLE response when no resource matches tasks."""
    app = _client_app(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/planning/solve",
            json=_request(resource_type="unavailable-specialty"),
            headers={"X-API-Key": "planning-analyst"},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "INFEASIBLE"
    assert "CP-SAT could not find a feasible schedule" in response.json()["message"]
    with Session(app.state.test_engine) as db:
        assert db.scalars(select(Schedule)).all() == []
    app.state.test_engine.dispose()
