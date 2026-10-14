"""Tests for initial ORM metadata and audit append-only enforcement."""

from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings
from backend.app.db.models import AuditEntry, Decision, RawEvent, Source

ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    ROOT / "backend" / "app" / "db" / "migrations" / "versions" / "0001_initial_schema.py"
)


def _initial_migration():
    """Load the initial migration module for direct SQLite verification."""
    spec = importlib.util.spec_from_file_location("initial_schema", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_initial_migration_creates_all_tables_and_indexes() -> None:
    """Create the schema and verify required tables and query indexes exist."""
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            _initial_migration().upgrade()

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "source",
        "raw_event",
        "record",
        "claim",
        "issue",
        "evidence_edge",
        "decision",
        "assumption",
        "dependency",
        "forecast",
        "schedule",
        "experiment_run",
        "agent_run",
        "verification_result",
        "approval",
        "audit_entry",
        "idempotency_record",
    } <= tables
    assert {index["name"] for index in inspector.get_indexes("record")} >= {
        "ix_record_entity_source"
    }
    assert {index["name"] for index in inspector.get_indexes("claim")} >= {"ix_claim_record"}
    assert {index["name"] for index in inspector.get_indexes("dependency")} >= {
        "ix_dependency_input_id"
    }

    engine.dispose()


def test_uuid_created_at_version_defaults_and_audit_immutability() -> None:
    """Use model defaults and reject audit-entry updates and deletes at the DB layer."""
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            _initial_migration().upgrade()

    with Session(engine) as db:
        source = Source(name="synthetic-grid", source_type="resource", reliability_prior=0.9)
        db.add(source)
        db.flush()
        assert source.id is not None
        assert isinstance(source.id, type(uuid4()))

        decision = Decision(
            decision_type="schedule",
            status="verified",
            ref_id=uuid4(),
        )
        db.add(decision)
        db.flush()
        assert decision.version == 1
        assert decision.created_at.tzinfo is not None

        raw_event = RawEvent(
            source_id=source.id,
            source_event_id="event-1",
            payload={"synthetic": True},
            event_time=datetime.now(UTC),
        )
        db.add(raw_event)
        db.flush()
        assert raw_event.ingest_time.tzinfo is not None

        audit = AuditEntry(
            entity_type="decision",
            entity_id=uuid4(),
            action="created",
            before_ref=None,
            after_ref={"version": 1},
            actor="test",
            correlation_id="test-correlation",
        )
        db.add(audit)
        db.commit()

        with pytest.raises(IntegrityError):
            audit.action = "changed"
            db.commit()
        db.rollback()

        audit_entry = db.scalar(select(AuditEntry))
        assert audit_entry is not None
        with pytest.raises(IntegrityError):
            db.delete(audit_entry)
            db.commit()
        db.rollback()

    engine.dispose()


def test_session_scope_commits_on_success_and_rolls_back_on_error(monkeypatch) -> None:
    """Manage script transactions with the documented session scope behavior."""
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    get_settings.cache_clear()
    try:
        db_session = importlib.import_module("backend.app.db.session")
        db_session.SessionLocal = sessionmaker(
            bind=db_session.engine,
            expire_on_commit=False,
        )

        setup = db_session.session_scope()
        setup_db = next(setup)
        setup_db.execute(text("CREATE TABLE sample (id INTEGER PRIMARY KEY)"))
        with pytest.raises(StopIteration):
            next(setup)

        failed = db_session.session_scope()
        failed_db = next(failed)
        failed_db.execute(text("INSERT INTO sample (id) VALUES (1)"))
        with pytest.raises(RuntimeError, match="rollback"):
            failed.throw(RuntimeError("rollback"))

        verify = db_session.session_scope()
        verify_db = next(verify)
        assert verify_db.scalar(text("SELECT count(*) FROM sample")) == 0
        with pytest.raises(StopIteration):
            next(verify)
        db_session.engine.dispose()
    finally:
        get_settings.cache_clear()
