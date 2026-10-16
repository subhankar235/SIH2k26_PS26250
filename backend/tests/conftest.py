"""Environment defaults for backend test collection."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

os.environ.setdefault("POSTGRES_USER", "airpower_test")
os.environ.setdefault("POSTGRES_PASSWORD", "airpower_test")
os.environ.setdefault("POSTGRES_DB", "airpower_test")
os.environ.setdefault("FRESHNESS_THRESHOLDS", '{"resource":3600,"crew":3600}')


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    """Create a test database using TEST_DATABASE_URL or isolated in-memory SQLite.

    CI can point ``TEST_DATABASE_URL`` at a disposable PostgreSQL container. The
    SQLite default keeps local unit runs self-contained when Docker is unavailable.
    """
    from backend.app.db import models as _models  # noqa: F401
    from backend.app.db.base import Base

    url = os.getenv("TEST_DATABASE_URL", "sqlite://")
    options = {"pool_pre_ping": True}
    if url.startswith("sqlite:"):
        options["connect_args"] = {"check_same_thread": False}
        if url in {"sqlite://", "sqlite:///:memory:"}:
            options["poolclass"] = StaticPool
    engine = create_engine(url, **options)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(test_engine: Engine) -> Iterator[Session]:
    """Yield a session enclosed in a rollback-only outer transaction."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def source_factory(db: Session):
    """Factory for uniquely named synthetic data sources."""
    from backend.app.db.models import Source

    def make_source(
        *,
        name: str | None = None,
        source_type: str = "resource",
        reliability_prior: float = 0.8,
    ) -> Source:
        source = Source(
            name=name or f"test-source-{uuid4()}",
            source_type=source_type,
            reliability_prior=reliability_prior,
        )
        db.add(source)
        db.flush()
        return source

    return make_source


@pytest.fixture
def record_factory(db: Session, source_factory):
    """Factory for versioned records with linked raw events and customizable fields."""
    from backend.app.db.models import RawEvent, Record

    def make_record(
        *,
        entity_id: str | None = None,
        source: object | None = None,
        source_type: str = "resource",
        payload: dict[str, object] | None = None,
        version: int = 1,
        flags: list[str] | None = None,
        event_time: datetime | None = None,
    ) -> Record:
        now = event_time or datetime.now(UTC)
        entity = entity_id or f"{source_type}:{uuid4()}"
        selected_source = source or source_factory(source_type=source_type)
        source_id = selected_source.id
        content = payload or {"entity_id": entity}
        raw_event = RawEvent(
            source_id=source_id,
            source_event_id=f"test-event-{uuid4()}",
            payload=content,
            event_time=now,
            ingest_time=now,
        )
        db.add(raw_event)
        db.flush()
        record = Record(
            entity_id=entity,
            source_type=source_type,
            normalised_payload=content,
            source_id=source_id,
            raw_event_id=raw_event.id,
            event_time=now,
            ingest_time=now,
            version=version,
            flags=flags or [],
        )
        db.add(record)
        db.flush()
        return record

    return make_record


@pytest.fixture
def claim_factory(db: Session, record_factory):
    """Factory for claims attached to a record and its owning source."""
    from backend.app.db.models import Claim

    def make_claim(
        *,
        record=None,
        attribute: str = "capacity_mw",
        value: object = 1.0,
        observed_at: datetime | None = None,
    ) -> Claim:
        selected_record = record or record_factory()
        claim = Claim(
            record_id=selected_record.id,
            attribute=attribute,
            value=value,
            source_id=selected_record.source_id,
            observed_at=observed_at or datetime.now(UTC),
        )
        db.add(claim)
        db.flush()
        return claim

    return make_claim


@pytest.fixture
def schedule_factory(db: Session):
    """Factory for small independently verifiable persisted schedule snapshots."""
    from backend.app.db.models import Schedule

    def make_schedule(
        *,
        assignments: list[dict[str, object]] | None = None,
        tasks: list[dict[str, object]] | None = None,
        resources: list[dict[str, object]] | None = None,
        status: str = "draft",
        solver_meta: dict[str, object] | None = None,
    ) -> Schedule:
        snapshot = solver_meta or {
            "problem": {
                "tasks": tasks
                or [
                    {
                        "id": "task-a",
                        "duration": 1,
                        "resource_type": "crew",
                        "earliest": 0,
                        "latest": 4,
                    }
                ],
                "resources": resources
                or [{"id": "crew-a", "type": "crew", "capacity": 1, "available": [[0, 5]]}],
                "precedence": [],
                "policies": [],
                "horizon": 5,
            },
            "input_versions": [],
        }
        schedule = Schedule(
            version=1,
            assignments=assignments
            or [{"task_id": "task-a", "resource_id": "crew-a", "start": 0, "end": 1}],
            objectives={"makespan": 1.0},
            solver_meta=snapshot,
            status=status,
            problem_hash="f" * 64,
        )
        db.add(schedule)
        db.flush()
        return schedule

    return make_schedule


@pytest.fixture
def api_headers() -> dict[str, dict[str, str]]:
    """Provide ready-to-use API key headers for common roles."""
    return {
        role: {"X-API-Key": f"test-{role}-key"}
        for role in ("viewer", "analyst", "approver", "admin")
    }


@pytest.fixture
def client(monkeypatch, api_headers: dict[str, dict[str, str]]) -> Iterator[TestClient]:
    """Create an isolated FastAPI test client with committed request sessions."""
    from backend.app.core import security
    from backend.app.core.deps import get_db
    from backend.app.db import models as _models  # noqa: F401
    from backend.app.db.base import Base
    from backend.app.main import create_app

    api_key_actors = {
        values["X-API-Key"]: {"id": f"test-{role}", "role": role}
        for role, values in api_headers.items()
    }
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(api_keys=api_key_actors),
    )
    app = create_app()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_db() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        test_client.headers.update(api_headers["analyst"])
        yield test_client
    engine.dispose()
