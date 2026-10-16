"""Unit tests for per-source ingestion payload validation."""

from __future__ import annotations

from backend.app.core.enums import SourceType
from backend.app.services.ingestion.validator import SCHEMAS, validate_event


def test_each_source_validates_valid_invalid_and_missing_payloads() -> None:
    """Validate one valid, wrong-type, and missing-field payload per source."""
    assert set(SCHEMAS) == set(SourceType)
    samples = {
        SourceType.RESOURCE: {"entity_id": "r-1", "capacity_mw": 2.5},
        SourceType.CREW: {"entity_id": "crew-1", "skills": ["repair"]},
        SourceType.AVAILABILITY: {"entity_id": "r-1", "available": True},
        SourceType.WEATHER: {"entity_id": "region-1", "temperature_c": 12.5},
        SourceType.CONSTRAINT: {"entity_id": "grid-1", "constraint_type": "capacity"},
    }

    for source, payload in samples.items():
        valid = validate_event(source, payload)
        invalid_type = validate_event(source, {**payload, "entity_id": 3})
        missing_field = validate_event(source, {"unrelated": "missing identity"})

        assert valid.ok and valid.model is not None
        assert invalid_type.ok is False
        assert invalid_type.errors
        assert missing_field.ok is False
        assert any("entity_id" in error for error in missing_field.errors)
