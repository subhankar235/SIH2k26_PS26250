"""Ingestion request, record, and source-health schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, Field

from backend.app.core.enums import SourceType
from backend.app.schemas.common import APIModel


class IngestEventIn(APIModel):
    """Describe a source event submitted for ingestion."""

    source: SourceType
    source_event_id: str = Field(min_length=1, max_length=255)
    event_time: AwareDatetime
    payload: dict[str, Any]


class RecordOut(APIModel):
    """Return a normalized, versioned record and its provenance ids."""

    id: UUID
    entity_id: str
    source_type: SourceType
    normalised_payload: dict[str, Any]
    version: int = Field(ge=1)
    source_id: UUID
    raw_event_id: UUID
    event_time: AwareDatetime
    ingest_time: AwareDatetime
    flags: list[str] = Field(default_factory=list)
    superseded_by: UUID | None = None


class TopicStatus(APIModel):
    """Describe ingestion health for one source topic."""

    topic: str
    status: str
    lag: int = Field(default=0, ge=0)


class IngestStatusOut(APIModel):
    """Return health information for all ingestion topics."""

    topics: list[TopicStatus]


class FlaggedRecordOut(APIModel):
    """Return a record with reasons it needs review."""

    record: RecordOut
    reasons: list[str] = Field(min_length=1)
