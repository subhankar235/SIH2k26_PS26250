"""Unit tests for stress execution and citation-grounded explanations."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core import security
from backend.app.core.config import get_settings
from backend.app.core.deps import get_db
from backend.app.core.exceptions import VerificationFailed
from backend.app.db.base import Base
from backend.app.db.models import AuditEntry, RawEvent, Record, Source
from backend.app.db.models.agent_run import AgentRun
from backend.app.db.models.experiment import ExperimentRun
from backend.app.main import create_app
from backend.app.schemas.agents import EvidenceRef
from backend.app.schemas.stress import StressRunIn
from backend.app.services.explanation.explainer import build_explanation, validate_citations
from backend.app.services.stress import run_manager
from simulation.runner.metrics import compute
from simulation.runner.run_scenario import Scenario, run


class _BackgroundQueue:
    """Capture FastAPI background jobs for deterministic service-level assertions."""

    def __init__(self) -> None:
        self.tasks: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    def add_task(self, function, *args, **kwargs) -> None:
        self.tasks.append((function, args, kwargs))


def _record(db: Session) -> Record:
    """Insert one concrete versioned record citation."""
    now = datetime.now(UTC)
    source = Source(name=f"citation-{uuid4()}", source_type="resource", reliability_prior=0.9)
    db.add(source)
    db.flush()
    event = RawEvent(
        source_id=source.id,
        source_event_id=f"event-{uuid4()}",
        payload={"entity_id": "resource:citation"},
        event_time=now,
        ingest_time=now,
    )
    db.add(event)
    db.flush()
    record = Record(
        entity_id="resource:citation",
        source_type="resource",
        normalised_payload={"entity_id": "resource:citation", "capacity_mw": 12},
        source_id=source.id,
        raw_event_id=event.id,
        event_time=now,
        ingest_time=now,
        version=1,
    )
    db.add(record)
    db.flush()
    return record


def test_stress_run_is_queued_then_executed_and_audited(monkeypatch) -> None:
    """Persist immediately, enqueue exactly once, then persist deterministic metrics."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(run_manager, "_session_factory", lambda: factory)
    queue = _BackgroundQueue()
    with Session(engine) as db:
        run_row = run_manager.start_run(
            db,
            StressRunIn(scenario="heavy_staleness", seed=31, severity=0.5),
            "stress-analyst",
            background_tasks=queue,  # type: ignore[arg-type]
        )
        db.commit()
        assert run_row.status == "queued"
        assert len(queue.tasks) == 1
        queued = run_manager.get_run(db, run_row.id)
        assert queued.scenario == "heavy_staleness"

    queued_function, args, kwargs = queue.tasks[0]
    assert queued_function is run_manager.execute_run
    assert kwargs == {}
    queued_function(*args)

    with Session(engine) as db:
        completed = db.get(ExperimentRun, run_row.id)
        assert completed is not None
        assert completed.status == "completed"
        assert completed.metrics["detection_recall"] == 1.0
        assert completed.metrics["baselines"]["no_detection"]["detection_recall"] == 0.0
        actions = db.scalars(
            select(AuditEntry.action).where(AuditEntry.entity_id == run_row.id)
        ).all()
        assert actions == ["queued", "status_changed", "status_changed"]
    engine.dispose()


def test_scenario_metrics_are_reproducible_from_seed() -> None:
    """Re-running the same synthetic scenario returns identical metrics."""
    first = run(Scenario("source_conflict", severity=0.3), seed=9)
    second = run(Scenario("source_conflict", severity=0.3), seed=9)

    assert first == second
    assert compute(first, first.labels) == compute(second, second.labels)


def test_citations_resolve_exact_record_versions_and_inline_sentence_links() -> None:
    """Resolve evidence rows and require inline markers on each sentence when used."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        record = _record(db)
        reference = EvidenceRef(kind="record", id=record.id, version=record.version)
        assert validate_citations(db, "Capacity is 12 MW.", [reference]) == []
        marker = f"[record:{record.id}:v{record.version}]"
        assert validate_citations(
            db,
            f"Capacity is 12 MW {marker}. The source is current {marker}.",
            [reference],
        ) == []
        incomplete = validate_citations(
            db,
            f"Capacity is 12 MW {marker}. The source is current.",
            [reference],
        )
        assert incomplete == ["sentence 2: missing inline evidence citation"]
        stale = EvidenceRef(kind="record", id=record.id, version=2)
        assert validate_citations(db, "Capacity is 12 MW.", [stale]) == [
            f"record:{record.id}:v2"
        ]
    engine.dispose()


def test_build_explanation_rejects_unresolved_evidence() -> None:
    """Reject persisted agent output that cites a missing row or version."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        run_row = AgentRun(
            request={},
            graph_state={},
            checkpoints=[],
            retries=0,
            status="completed",
            explanation={
                "text": "The resource is available.",
                "evidence_refs": [
                    {"kind": "record", "id": str(uuid4()), "version": 1}
                ],
            },
        )
        db.add(run_row)
        db.flush()
        with pytest.raises(VerificationFailed, match="unresolved"):
            build_explanation(db, run_row)
    engine.dispose()


def test_stress_api_enqueues_and_polls_to_completion(monkeypatch) -> None:
    """Exercise the actual 202 route and its background simulation task."""
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            api_keys={"stress-analyst": {"id": "stress-api-user", "role": "analyst"},
                      "stress-viewer": {"id": "stress-api-viewer", "role": "viewer"}}
        ),
    )
    app: FastAPI = create_app(get_settings())
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        run_manager,
        "_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False),
    )

    def session_override() -> Iterator[Session]:
        with Session(engine) as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = session_override
    with TestClient(app) as client:
        started = client.post(
            "/api/v1/stress/runs",
            json={"scenario": "heavy_staleness", "seed": 7, "severity": 0.25},
            headers={"X-API-Key": "stress-analyst"},
        )
        assert started.status_code == 202, started.text
        run_id = started.json()["id"]
        assert started.json()["status"] == "queued"
        polled = client.get(
            f"/api/v1/stress/runs/{run_id}",
            headers={"X-API-Key": "stress-viewer"},
        )

    assert polled.status_code == 200, polled.text
    assert polled.json()["status"] == "completed"
    assert "detection_recall" in polled.json()["metrics"]
    engine.dispose()
