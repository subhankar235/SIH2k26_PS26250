"""Validate source payloads without dropping malformed events."""

from __future__ import annotations

from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.app.core.enums import SourceType
from backend.app.schemas.common import APIModel


class SourcePayload(APIModel):
    """Shared identity and event-time fields for synthetic source events."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    entity_id: str = Field(min_length=1, max_length=255)
    event_time: AwareDatetime | None = None


class ResourcePayload(SourcePayload):
    """Validate synthetic resource state and capacity fields."""

    resource_type: str | None = Field(default=None, min_length=1)
    capacity_mw: float | None = Field(default=None, ge=0)
    status: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class CrewPayload(SourcePayload):
    """Validate synthetic crew identity, skills, and availability."""

    role: str | None = None
    skills: list[str] = Field(default_factory=list)
    available_hours: float | None = Field(default=None, ge=0)


class AvailabilityPayload(SourcePayload):
    """Validate synthetic resource or crew availability windows."""

    available: bool | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_window(self) -> AvailabilityPayload:
        """Reject availability windows whose end precedes their start."""
        if self.starts_at and self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("ends_at must not precede starts_at")
        return self


class WeatherPayload(SourcePayload):
    """Validate synthetic weather measurements."""

    region: str | None = None
    temperature_c: float | None = None
    wind_speed_mps: float | None = Field(default=None, ge=0)
    precipitation_mm: float | None = Field(default=None, ge=0)
    conditions: str | None = None


class ConstraintPayload(SourcePayload):
    """Validate synthetic operational constraints."""

    constraint_type: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None


SCHEMAS: dict[SourceType, type[BaseModel]] = {
    SourceType.RESOURCE: ResourcePayload,
    SourceType.CREW: CrewPayload,
    SourceType.AVAILABILITY: AvailabilityPayload,
    SourceType.WEATHER: WeatherPayload,
    SourceType.CONSTRAINT: ConstraintPayload,
}


class ValidationResult(BaseModel):
    """Return validation state, human-readable errors, and the typed payload."""

    ok: bool
    errors: list[str]
    model: BaseModel | None = None


def validate_event(source: SourceType, payload: dict[str, Any]) -> ValidationResult:
    """Validate an event against the Pydantic model registered for its source.

    Args:
        source: Source category that selects the payload schema.
        payload: Untrusted synthetic event payload.

    Returns:
        Validation status, formatted errors, and the validated source model on success.

    Raises:
        None for invalid event data; validation failures are returned in the result.
    """
    schema = SCHEMAS[source]
    try:
        model = schema.model_validate(payload)
    except ValidationError as error:
        errors = [
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors()
        ]
        return ValidationResult(ok=False, errors=errors)
    return ValidationResult(ok=True, errors=[], model=model)
