"""Append-only audit query and response schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from backend.app.schemas.common import APIModel


class AuditEntryOut(APIModel):
    """Return a minimal audit entry without full record payloads."""

    id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    before_ref: dict[str, Any] | None = None
    after_ref: dict[str, Any] | None = None
    actor: str
    correlation_id: str
    created_at: AwareDatetime


class AuditQuery(APIModel):
    """Filter audit results by entity, actor, or action."""

    entity_type: str | None = None
    entity_id: UUID | None = None
    actor: str | None = None
    action: str | None = None
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> AuditQuery:
        """Ensure the audit query's time range is ordered."""
        if self.since and self.until and self.until < self.since:
            raise ValueError("until must not precede since")
        return self
