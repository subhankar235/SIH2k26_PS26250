"""Append-only audit write and query operations."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from backend.app.core.logging import correlation_id_var
from backend.app.db.models.audit_log import AuditEntry
from backend.app.schemas.audit import AuditEntryOut, AuditQuery
from backend.app.schemas.common import Page

_MAX_DIFF_BYTES = 16_384


def _validate_diff(value: dict[str, Any] | None, field: str) -> None:
    """Require audit before/after snapshots to remain small JSON references/diffs."""
    if value is None:
        return
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError) as error:
        raise ValueError(f"audit {field} reference must be JSON serializable") from error
    if len(encoded.encode("utf-8")) > _MAX_DIFF_BYTES:
        raise ValueError(f"audit {field} reference exceeds {_MAX_DIFF_BYTES} bytes")


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

    Raises:
        ValueError: If entity/action/actor is empty or a before/after diff is too large.
        SQLAlchemyError: If the audit row cannot be flushed.
    """
    if not entity_type.strip() or not action.strip() or not actor.strip():
        raise ValueError("audit entity_type, action, and actor must not be empty")
    _validate_diff(before, "before")
    _validate_diff(after, "after")
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


def query(
    db: Session,
    filters: AuditQuery,
    limit: int,
    offset: int,
) -> Page[AuditEntryOut]:
    """Return filtered audit entries newest first with a total count."""
    if limit < 1 or offset < 0:
        raise ValueError("audit pagination requires limit >= 1 and offset >= 0")
    predicates = []
    if filters.entity_type is not None:
        predicates.append(AuditEntry.entity_type == filters.entity_type)
    if filters.entity_id is not None:
        predicates.append(AuditEntry.entity_id == filters.entity_id)
    if filters.actor is not None:
        predicates.append(AuditEntry.actor == filters.actor)
    if filters.action is not None:
        predicates.append(AuditEntry.action == filters.action)
    if filters.since is not None:
        predicates.append(AuditEntry.created_at >= filters.since)
    if filters.until is not None:
        predicates.append(AuditEntry.created_at <= filters.until)
    where = and_(*predicates) if predicates else None
    statement = select(AuditEntry)
    count_statement = select(func.count()).select_from(AuditEntry)
    if where is not None:
        statement = statement.where(where)
        count_statement = count_statement.where(where)
    items = list(
        db.scalars(
            statement.order_by(AuditEntry.created_at.desc(), AuditEntry.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    total = int(db.scalar(count_statement) or 0)
    return Page[AuditEntryOut](items=items, total=total, limit=limit, offset=offset)


def history(db: Session, entity_type: str, entity_id: uuid.UUID) -> list[AuditEntry]:
    """Return the chronological append-only audit history for one entity."""
    if not entity_type.strip():
        raise ValueError("audit entity_type must not be empty")
    return list(
        db.scalars(
            select(AuditEntry)
            .where(AuditEntry.entity_type == entity_type, AuditEntry.entity_id == entity_id)
            .order_by(AuditEntry.created_at, AuditEntry.id)
        ).all()
    )
