"""Normalize source event identity, payload, and UTC timestamps."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict

from backend.app.core.enums import SourceType
from backend.app.schemas.common import APIModel


class NormalisedRecord(APIModel):
    """Carry a canonical source record before it is persisted."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    source: SourceType
    entity_id: str
    normalised_payload: dict[str, Any]
    event_time: AwareDatetime
    ingest_time: AwareDatetime
    extras: dict[str, Any]


def to_utc(ts: str | datetime) -> datetime:
    """Parse a timestamp and return it as a timezone-aware UTC datetime.

    Args:
        ts: ISO-8601 timestamp or datetime value.

    Returns:
        The timestamp converted to UTC; naive timestamps are interpreted as UTC.

    Raises:
        ValueError: If the string is not a valid ISO-8601 datetime.
    """
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def canonical_entity_id(source: SourceType, raw_id: str) -> str:
    """Namespace and normalize an external entity identifier.

    Args:
        source: Source category for namespacing the identifier.
        raw_id: Original source-specific id.

    Returns:
        A stable, case-normalized entity identifier.

    Raises:
        ValueError: If the identifier is empty after normalization.
    """
    normalized = unicodedata.normalize("NFKC", raw_id).strip().casefold()
    normalized = re.sub(r"\s+", "-", normalized)
    if not normalized:
        raise ValueError("entity id must not be empty")
    return f"{source.value}:{normalized}"


def normalise(source: SourceType, model: BaseModel, ingest_time: datetime) -> NormalisedRecord:
    """Normalize a validated source model into a canonical record payload.

    Args:
        source: Source category associated with the payload.
        model: Validated per-source Pydantic model.
        ingest_time: Timestamp at which the service accepted the event.

    Returns:
        Canonical entity id, normalized payload, and both UTC timestamps.

    Raises:
        ValueError: If the model does not contain an entity identifier.
    """
    values = model.model_dump(mode="json", exclude_none=True)
    raw_id = values.pop("entity_id", None)
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise ValueError("validated source payload does not contain entity_id")

    event_time_value = values.pop("event_time", None)
    event_time = to_utc(event_time_value) if event_time_value else to_utc(ingest_time)
    known_fields = set(type(model).model_fields)
    extras = {
        key: value
        for key, value in values.items()
        if key not in known_fields and key != "event_time"
    }
    normalized_values = {
        key: value for key, value in values.items() if key in known_fields and key != "event_time"
    }
    if "capacity_kw" in values and "capacity_mw" not in normalized_values:
        normalized_values["capacity_mw"] = float(values["capacity_kw"]) / 1000.0
    if "wind_speed_kph" in values and "wind_speed_mps" not in normalized_values:
        normalized_values["wind_speed_mps"] = float(values["wind_speed_kph"]) / 3.6
    if "temperature_f" in values and "temperature_c" not in normalized_values:
        normalized_values["temperature_c"] = (float(values["temperature_f"]) - 32.0) * 5.0 / 9.0
    for field in ("status", "resource_type", "constraint_type", "conditions"):
        if isinstance(normalized_values.get(field), str):
            normalized_values[field] = normalized_values[field].strip().casefold()
    if extras:
        normalized_values["extras"] = extras
    normalized_values["entity_id"] = canonical_entity_id(source, raw_id)

    return NormalisedRecord(
        source=source,
        entity_id=canonical_entity_id(source, raw_id),
        normalised_payload=normalized_values,
        event_time=event_time,
        ingest_time=to_utc(ingest_time),
        extras=extras,
    )
