"""Create the initial backend schema and append-only audit trigger."""

from __future__ import annotations

from alembic import op

from backend.app.db import models as _models  # noqa: F401
from backend.app.db.base import Base

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all mapped tables, indexes, and audit immutability triggers.

    Returns:
        None.
    """
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name == "postgresql":
        op.execute("""
            CREATE OR REPLACE FUNCTION reject_audit_entry_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'audit_entry is append-only';
            END;
            $$ LANGUAGE plpgsql;
            """)
        op.execute("""
            CREATE TRIGGER audit_entry_append_only
            BEFORE UPDATE OR DELETE ON audit_entry
            FOR EACH ROW EXECUTE FUNCTION reject_audit_entry_mutation();
            """)
    elif bind.dialect.name == "sqlite":
        op.execute("""
            CREATE TRIGGER audit_entry_no_update
            BEFORE UPDATE ON audit_entry
            BEGIN SELECT RAISE(ABORT, 'audit_entry is append-only'); END;
            """)
        op.execute("""
            CREATE TRIGGER audit_entry_no_delete
            BEFORE DELETE ON audit_entry
            BEGIN SELECT RAISE(ABORT, 'audit_entry is append-only'); END;
            """)


def downgrade() -> None:
    """Remove the append-only triggers and initial mapped schema.

    Returns:
        None.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_entry_append_only ON audit_entry")
        op.execute("DROP FUNCTION IF EXISTS reject_audit_entry_mutation()")
    elif bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS audit_entry_no_update")
        op.execute("DROP TRIGGER IF EXISTS audit_entry_no_delete")
    Base.metadata.drop_all(bind=bind)
