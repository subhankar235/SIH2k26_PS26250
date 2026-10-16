"""End-to-end tests for incremental replanning and verified replacement."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from uuid import UUID

import pytest
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
from backend.app.db.models import (
    AuditEntry,
    Decision,
    RawEvent,
    Record,
    Schedule,
    Source,
    VerificationResult,
)
from backend.app.main import create_app
from optimisation.models.solution import Solution


def _client_app(monkeypatch) -> FastAPI:
    """Create an isolated app and SQLite database with an analyst credential."""
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            api_keys={"replan-analyst": {"id": "planner-replan", "role": "analyst"}}
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


def _create_source_record(app: FastAPI) -> UUID:
    """Seed one versioned task input and return its record id."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    with Session(app.state.test_engine) as db:
        source = Source(name="replan-source", source_type="resource", reliability_prior=0.8)
        db.add(source)
        db.flush()
        event = RawEvent(
            source_id=source.id,
            source_event_id="replan-source-v1",
            payload={"entity_id": "resource:replan"},
            event_time=now,
            ingest_time=now,
        )
        db.add(event)
        db.flush()
        record = Record(
            entity_id="resource:replan",
            source_type="resource",
            normalised_payload={"entity_id": "resource:replan"},
            source_id=source.id,
            raw_event_id=event.id,
            event_time=now,
            ingest_time=now,
            version=1,
        )
        db.add(record)
        db.commit()
        return record.id


def _solve_request(record_id: UUID) -> dict[str, object]:
    """Build a small two-task problem with one task tied to the changed record."""
    return {
        "problem": {
            "tasks": [
                {
                    "id": "affected-task",
                    "duration": 2,
                    "resource_type": "crew",
                    "record_id": str(record_id),
                },
                {"id": "unaffected-task", "duration": 1, "resource_type": "crew"},
            ],
            "resources": [
                {"id": "crew-a", "type": "crew", "capacity": 1, "available": [[0, 10]]}
            ],
            "windows": {"horizon": 10},
            "precedence": [],
            "policies": [],
            "objectives": {"makespan": 1.0},
        },
        "use_alns": False,
        "time_limit_s": 4,
        "seed": 17,
    }


def _supersede_record(app: FastAPI, record_id: UUID) -> UUID:
    """Insert version two and link it as the active record version."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    with Session(app.state.test_engine) as db:
        old = db.get(Record, record_id)
        assert old is not None
        event = RawEvent(
            source_id=old.source_id,
            source_event_id="replan-source-v2",
            payload={"entity_id": old.entity_id},
            event_time=now,
            ingest_time=now,
        )
        db.add(event)
        db.flush()
        new = Record(
            entity_id=old.entity_id,
            source_type=old.source_type,
            normalised_payload={"entity_id": old.entity_id, "updated": True},
            source_id=old.source_id,
            raw_event_id=event.id,
            event_time=now,
            ingest_time=now,
            version=2,
        )
        db.add(new)
        db.flush()
        old.superseded_by = new.id
        db.commit()
        return new.id


@pytest.mark.parametrize("mode", ["incremental", "fallback", "uncertain"])
def test_replanning_api_verifies_replacement_before_superseding_old_schedule(
    monkeypatch, mode: str
) -> None:
    """Retain the parent link, fallback when incremental solve fails, and audit changes."""
    app = _client_app(monkeypatch)
    old_record_id = _create_source_record(app)
    headers = {"X-API-Key": "replan-analyst"}
    with TestClient(app) as client:
        original_response = client.post(
            "/api/v1/planning/solve",
            json=_solve_request(old_record_id),
            headers=headers,
        )
        assert original_response.status_code == 200, original_response.text
        original_id = UUID(original_response.json()["id"])
        new_record_id = _supersede_record(app, old_record_id)

        if mode == "fallback":
            from backend.app.services.replanning import incremental_recompute

            original_solve = incremental_recompute.solve
            calls = 0

            def fail_first_solve(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    return Solution(
                        assignments=[],
                        objectives={},
                        status="INFEASIBLE",
                        wall_time_s=0.0,
                        seed=17,
                    )
                return original_solve(*args, **kwargs)

            monkeypatch.setattr(incremental_recompute, "solve", fail_first_solve)
        elif mode == "uncertain":
            from backend.app.services.replanning import incremental_recompute

            def uncertain_checks(db, target_type: str, target_id: UUID, actor: str):
                result = VerificationResult(
                    target_type=target_type,
                    target_id=target_id,
                    outcome="uncertain",
                    violations=[],
                    uncertainty_flags=[{"code": "TEST_UNCERTAINTY", "message": "review"}],
                )
                db.add(result)
                db.flush()
                return result

            monkeypatch.setattr(incremental_recompute, "run_checks", uncertain_checks)

        response = client.post(
            "/api/v1/replanning/run",
            json={
                "schedule_id": str(original_id),
                "changes": [
                    {
                        "input_type": "record",
                        "input_id": str(new_record_id),
                        "old_version": 1,
                        "new_version": 2,
                    }
                ],
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        new_id = UUID(response.json()["schedule"]["id"])
        diff_response = client.get(
            f"/api/v1/replanning/diff/{original_id}/{new_id}", headers=headers
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    new_schedule_id = UUID(payload["schedule"]["id"])
    assert payload["schedule"]["parent_schedule_id"] == str(original_id)
    expected_status = "uncertain" if mode == "uncertain" else "verified"
    assert payload["schedule"]["status"] == expected_status
    assert payload["fallback_to_full_solve"] is (mode == "fallback")
    assert payload["diff"]["unchanged"] + len(payload["diff"]["moved"]) == 2
    assert diff_response.status_code == 200, diff_response.text
    assert diff_response.json() == payload["diff"]

    with Session(app.state.test_engine) as db:
        old_schedule = db.get(Schedule, original_id)
        new_schedule = db.get(Schedule, new_schedule_id)
        assert old_schedule is not None and new_schedule is not None
        assert old_schedule.status == (
            "verified" if mode == "uncertain" else "superseded"
        )
        assert new_schedule.status == expected_status
        assert new_schedule.parent_schedule_id == old_schedule.id
        assert new_schedule.solver_meta["input_versions"] == [
            {
                "input_type": "record",
                "input_id": str(new_record_id),
                "input_version": 2,
            }
        ]
        decisions = db.scalars(select(Decision).order_by(Decision.created_at, Decision.id)).all()
        assert [decision.status for decision in decisions] == ["stale", expected_status]
        old_audits = db.scalars(
            select(AuditEntry).where(
                AuditEntry.entity_type == "schedule",
                AuditEntry.entity_id == original_id,
            )
        ).all()
        assert any(entry.action == "superseded" for entry in old_audits) is (mode != "uncertain")
    app.state.test_engine.dispose()
