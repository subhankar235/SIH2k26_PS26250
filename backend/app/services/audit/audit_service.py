"""Append-only audit write and query operations."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from backend.app.core.logging import correlation_id_var
from backend.app.db.models.audit_log import AuditEntry


def record(
    db: Session,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    actor: str,
) -> AuditEntry:
    """Append an audit entry in the caller's transaction.

    Args:
        db: Active synchronous database session.
        entity_type: Domain type of the changed entity.
        entity_id: UUID of the changed entity.
        action: Short state-change label.
        before: Small prior-state reference or diff.
        after: Small new-state reference or diff.
        actor: Actor responsible for the change.

    Returns:
        The flushed append-only audit entry.
    """
    entry = AuditEntry(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before_ref=before,
        after_ref=after,
        actor=actor,
        correlation_id=correlation_id_var.get(),
    )
    db.add(entry)
    db.flush()
    return entry
