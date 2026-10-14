"""Tests for A3 domain schema validation and ORM configuration."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from backend.app.schemas.agents import EvidenceRef, ExplanationOut
from backend.app.schemas.common import APIModel
from backend.app.schemas.forecast import ForecastPoint
from backend.app.schemas.ingestion import IngestEventIn
from backend.app.schemas.planning import Assignment


def test_explanation_requires_at_least_one_evidence_reference() -> None:
    """Reject explanations that contain no citations."""
    with pytest.raises(ValueError):
        ExplanationOut(text="A grounded claim.", evidence_refs=[])

    explanation = ExplanationOut(
        text="A grounded claim.",
        evidence_refs=[EvidenceRef(kind="record", id=uuid4(), version=1)],
    )
    assert len(explanation.evidence_refs) == 1


def test_event_time_requires_timezone_information() -> None:
    """Reject naive event timestamps at the API boundary."""
    with pytest.raises(ValueError):
        IngestEventIn(
            source="resource",
            source_event_id="event-1",
            event_time=datetime(2026, 1, 1),
            payload={"synthetic": True},
        )

    event = IngestEventIn(
        source="resource",
        source_event_id="event-1",
        event_time=datetime(2026, 1, 1, tzinfo=UTC),
        payload={"synthetic": True},
    )
    assert event.event_time.utcoffset() is not None


@pytest.mark.parametrize(
    "schema",
    [IngestEventIn, ExplanationOut, ForecastPoint, Assignment],
)
def test_domain_schemas_inherit_from_attributes_config(schema: type[APIModel]) -> None:
    """Keep response schemas compatible with ORM model attributes."""
    assert schema.model_config["from_attributes"] is True


def test_forecast_interval_and_assignment_window_are_validated() -> None:
    """Reject inverted confidence intervals and invalid schedule windows."""
    with pytest.raises(ValueError):
        ForecastPoint(
            t=datetime(2026, 1, 1, tzinfo=UTC),
            mean=1,
            lower=2,
            upper=0,
        )
    with pytest.raises(ValueError):
        Assignment(task_id="task", resource_id="resource", start=10, end=10)
