"""Add creation timestamps to forecast and schedule version rows."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0002_versioned_inputs_created_at"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

_TABLES = ("forecast", "schedule")


def upgrade() -> None:
    """Add server-populated creation timestamps when absent.

    Returns:
        None.
    """
    inspector = inspect(op.get_bind())
    for table in _TABLES:
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "created_at" not in columns:
            op.add_column(
                table,
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),
            )
            inspector = inspect(op.get_bind())


def downgrade() -> None:
    """Remove version-row creation timestamps if present.

    Returns:
        None.
    """
    inspector = inspect(op.get_bind())
    for table in reversed(_TABLES):
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "created_at" in columns:
            op.drop_column(table, "created_at")
            inspector = inspect(op.get_bind())
