"""Database-level checks for append-only audit row enforcement."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import AuditEntry

ROOT = Path(__file__).resolve().parents[3]
MIGRATION_FILE = (
    ROOT / "backend" / "app" / "db" / "migrations" / "versions" / "0001_initial_schema.py"
)


def test_audit_rows_cannot_be_updated_or_deleted_at_database_level() -> None:
    """Run the initial migration and confirm the DB triggers reject mutations."""
    spec = importlib.util.spec_from_file_location("audit_initial_schema", MIGRATION_FILE)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
    try:
        with Session(engine) as db:
            row = AuditEntry(
                entity_type="schedule",
                entity_id=uuid4(),
                action="created",
                before_ref=None,
                after_ref={"status": "draft"},
                actor="test",
                correlation_id="audit-append-only-test",
            )
            db.add(row)
            db.commit()
            with pytest.raises(IntegrityError):
                row.action = "modified"
                db.commit()
            db.rollback()
            stored = db.scalar(select(AuditEntry))
            assert stored is not None and stored.action == "created"
            with pytest.raises(IntegrityError):
                db.delete(stored)
                db.commit()
            db.rollback()
            assert db.scalar(select(AuditEntry.id)) == row.id
    finally:
        engine.dispose()
