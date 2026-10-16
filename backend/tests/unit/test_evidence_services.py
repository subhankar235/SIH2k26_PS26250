"""Tests for evidence issue detection, graphing, provenance, and uncertainty."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import networkx as nx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.core.enums import IssueClass, SourceType
from backend.app.db.base import Base
from backend.app.db.models import AuditEntry, Claim, Issue, RawEvent, Record, Source
from backend.app.services.evidence.autopsy import build_autopsy, missing_information
from backend.app.services.evidence.contradiction_detector import (
    find_conflicts,
    find_duplicates,
    find_missing,
)
from backend.app.services.evidence.evidence_graph import build_graph, neighbours
from backend.app.services.evidence.provenance_tracer import trace, version_chain
from backend.app.services.evidence.staleness_checker import find_stale, is_stale
from backend.app.services.evidence.uncertainty import claim_belief, source_reliability


def _insert_source_record(
    db: Session,
    name: str,
    entity_id: str,
    value: float,
    now: datetime,
) -> tuple[Source, Record, Claim]:
    """Create linked source, raw event, record, and claim test fixtures."""
    source = Source(name=name, source_type=SourceType.RESOURCE.value, reliability_prior=0.8)
    db.add(source)
    db.flush()
    raw_event = RawEvent(
        source_id=source.id,
        source_event_id=f"{name}-event",
        payload={"entity_id": entity_id, "capacity_mw": value},
        event_time=now,
        ingest_time=now,
    )
    db.add(raw_event)
    db.flush()
    record = Record(
        entity_id=entity_id,
        source_type=SourceType.RESOURCE.value,
        normalised_payload={"entity_id": entity_id, "capacity_mw": value},
        source_id=source.id,
        raw_event_id=raw_event.id,
        event_time=now,
        ingest_time=now,
    )
    db.add(record)
    db.flush()
    claim = Claim(
        record_id=record.id,
        attribute="capacity_mw",
        value=value,
        source_id=source.id,
        observed_at=now,
    )
    db.add(claim)
    db.flush()
    return source, record, claim


def _db_session() -> tuple[object, Session]:
    """Create a SQLite database containing all backend tables."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def test_staleness_detection_uses_source_threshold_and_deduplicates_issues() -> None:
    """Detect old events and create one audited issue per stale record."""
    engine, db = _db_session()
    now = datetime.now(UTC)
    _, record, _ = _insert_source_record(
        db, "feed-stale", "resource:stale", 4.0, now - timedelta(hours=4)
    )
    db.commit()

    assert is_stale(record, now, {SourceType.RESOURCE: 3600})
    assert not is_stale(record, now, {SourceType.RESOURCE: 24 * 3600})
    first = find_stale(db, now)
    second = find_stale(db, now + timedelta(minutes=5))

    assert len(first) == len(second) == 1
    assert first[0].id == second[0].id
    assert first[0].issue_class == IssueClass.STALE.value
    assert db.scalar(select(AuditEntry).where(AuditEntry.entity_id == first[0].id)) is not None
    db.close()
    engine.dispose()


def test_conflicts_duplicates_and_missing_fields() -> None:
    """Detect competing values, repeated claims, and absent required fields."""
    engine, db = _db_session()
    now = datetime.now(UTC)
    _, record_a, claim_a = _insert_source_record(db, "feed-a", "resource:x", 4.0, now)
    _, record_b, claim_b = _insert_source_record(db, "feed-b", "resource:x", 5.0, now)
    source_c, record_c, _ = _insert_source_record(db, "feed-c", "resource:x", 4.0, now)
    duplicate_claim = Claim(
        record_id=record_c.id,
        attribute="capacity_mw",
        value=4.0,
        source_id=source_c.id,
        observed_at=now,
    )
    db.add(duplicate_claim)
    missing_record = Record(
        entity_id="resource:missing",
        source_type=SourceType.RESOURCE.value,
        source_id=source_c.id,
        raw_event_id=record_c.raw_event_id,
        event_time=now,
        ingest_time=now,
        flags=["invalid"],
        normalised_payload={
            "entity_id": "resource:missing",
            "validation_errors": ["capacity_mw: Input should be a valid number"],
        },
    )
    db.add(missing_record)
    db.commit()

    conflicts = find_conflicts(db, "resource:x", "capacity_mw")
    duplicates = find_duplicates(db)
    missing = find_missing(db, {SourceType.RESOURCE: ["capacity_mw"]})

    assert len(conflicts) == 1
    assert set(conflicts[0].claim_ids) >= {str(claim_a.id), str(claim_b.id)}
    assert len(duplicates) == 1
    assert duplicates[0].issue_class == IssueClass.DUPLICATE.value
    assert any(issue.details["record_id"] == str(missing_record.id) for issue in missing)
    assert any(
        "capacity_mw" in error for issue in missing for error in issue.details["missing_fields"]
    )
    db.close()
    engine.dispose()


def test_graph_neighbors_and_provenance_chain() -> None:
    """Build provenance edges and return a bounded graph neighborhood."""
    engine, db = _db_session()
    now = datetime.now(UTC)
    _, record, _ = _insert_source_record(db, "feed-graph", "resource:g", 8.0, now)
    _insert_source_record(db, "feed-other", "resource:other", 3.0, now)
    next_record = Record(
        entity_id=record.entity_id,
        source_type=record.source_type,
        normalised_payload={"entity_id": record.entity_id, "capacity_mw": 9.0},
        source_id=record.source_id,
        raw_event_id=record.raw_event_id,
        event_time=now + timedelta(minutes=1),
        ingest_time=now + timedelta(minutes=1),
        version=2,
    )
    db.add(next_record)
    db.flush()
    record.superseded_by = next_record.id
    db.commit()

    graph = build_graph(db, [record.entity_id, "resource:other"])
    root = f"record:{record.id}"
    neighborhood = neighbours(graph, root, depth=1)
    chain = version_chain(db, record.id)
    timeline = trace(db, next_record.id)

    assert graph.nodes[root]["kind"] == "record"
    assert any(data["relation"] == "about" for _, _, data in graph.edges(data=True))
    assert len(neighborhood) < len(graph)
    assert [item.version for item in chain] == [1, 2]
    assert any(step.action == "ingested" for step in timeline)
    assert any(step.action == "superseded" for step in timeline)
    db.close()
    engine.dispose()


def test_uncertainty_is_seeded_and_autopsy_contains_claims_provenance() -> None:
    """Produce reproducible reliability estimates and a complete issue autopsy."""
    engine, db = _db_session()
    now = datetime.now(UTC)
    source_a, record_a, claim_a = _insert_source_record(db, "feed-u1", "resource:u", 10.0, now)
    source_b, record_b, claim_b = _insert_source_record(db, "feed-u2", "resource:u", 12.0, now)
    issue = Issue(
        issue_class=IssueClass.CONFLICT.value,
        claim_ids=[str(claim_a.id), str(claim_b.id)],
        detected_at=now,
        status="open",
        details={
            "entity_id": record_a.entity_id,
            "attribute": "capacity_mw",
            "claims": [
                {
                    "claim_id": str(claim_a.id),
                    "record_id": str(record_a.id),
                    "attribute": claim_a.attribute,
                    "value": claim_a.value,
                    "source_id": str(source_a.id),
                    "observed_at": now.isoformat(),
                },
                {
                    "claim_id": str(claim_b.id),
                    "record_id": str(record_b.id),
                    "attribute": claim_b.attribute,
                    "value": claim_b.value,
                    "source_id": str(source_b.id),
                    "observed_at": now.isoformat(),
                },
            ],
        },
    )
    db.add(issue)
    db.commit()

    first = source_reliability(db, seed=17)
    second = source_reliability(db, seed=17)
    beliefs = claim_belief(issue, first)
    autopsy = build_autopsy(db, issue.id)

    assert first == second
    assert set(first) == {source_a.id, source_b.id}
    assert len(beliefs) == 2
    assert len(autopsy.claims) == 2
    assert autopsy.provenance
    assert autopsy.uncertainty["sources"]
    assert isinstance(autopsy.issue.id, UUID)
    db.close()
    engine.dispose()


def test_missing_information_reports_unlinked_conflict_claims() -> None:
    """Surface missing claim links in evidence issue explanations."""
    issue = Issue(
        issue_class=IssueClass.CONFLICT.value,
        claim_ids=[str(UUID(int=1))],
        detected_at=datetime.now(UTC),
        status="open",
        details={},
    )
    result = missing_information(issue, nx.MultiDiGraph())
    assert any("not present" in item for item in result)
