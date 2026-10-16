"""Persist queued/running/completed/failed stress-run state."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0003_experiment_run_status"
down_revision = "0002_versioned_inputs_created_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add a queued-default lifecycle status to experiment runs."""
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("experiment_run")}
    if "status" not in columns:
        op.add_column(
            "experiment_run",
            sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        )


def downgrade() -> None:
    """Remove the stress-run lifecycle status column."""
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("experiment_run")}
    if "status" in columns:
        op.drop_column("experiment_run", "status")
