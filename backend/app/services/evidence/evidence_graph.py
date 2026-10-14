"""Build a timestamped evidence provenance graph."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import networkx as nx  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.claim import Claim, EvidenceEdge
from backend.app.db.models.record import RawEvent, Record
from backend.app.db.models.source import Source


def _record_node(record_id: UUID) -> str:
    """Return a stable graph node id for a record."""
    return f"record:{record_id}"


def _claim_node(claim_id: UUID) -> str:
    """Return a stable graph node id for a claim."""
    return f"claim:{claim_id}"


def _source_node(source_id: UUID) -> str:
    """Return a stable graph node id for a source."""
    return f"source:{source_id}"


def _timestamp(value: datetime) -> str:
    """Serialize an event timestamp as ISO-8601."""
    return value.isoformat()


def build_graph(db: Session, entity_ids: list[str] | None = None) -> nx.MultiDiGraph:
    """Build the evidence graph for selected entities or all persisted entities.

    Args:
        db: Active synchronous database session.
        entity_ids: Optional canonical entity ids to include.

    Returns:
        A directed multigraph with record, claim, source, and entity nodes.

    Raises:
        SQLAlchemyError: If graph source data cannot be queried.
    """
    graph = nx.MultiDiGraph()
    record_query = select(Record)
    if entity_ids is not None:
        if not entity_ids:
            return graph
        record_query = record_query.where(Record.entity_id.in_(entity_ids))
    records = db.scalars(record_query.order_by(Record.entity_id, Record.version)).all()
    record_ids = {record.id for record in records}
    edge_endpoint_ids = {
        str(identifier)
        for record in records
        for identifier in (record.id, record.source_id, record.raw_event_id)
    }
    sources: dict[UUID, Source] = {}

    for record in records:
        source = db.get(Source, record.source_id)
        if source is not None:
            sources[source.id] = source
        record_node = _record_node(record.id)
        source_node = _source_node(record.source_id)
        entity_node = f"entity:{record.entity_id}"
        graph.add_node(
            record_node,
            kind="record",
            id=str(record.id),
            entity_id=record.entity_id,
            source_type=record.source_type,
            version=record.version,
            event_time=_timestamp(record.event_time),
            ingest_time=_timestamp(record.ingest_time),
        )
        graph.add_node(entity_node, kind="entity", id=record.entity_id)
        graph.add_node(source_node, kind="source", id=str(record.source_id))
        graph.add_edge(
            record_node,
            source_node,
            key="asserted_by",
            relation="asserted_by",
            timestamp=_timestamp(record.ingest_time),
        )
        graph.add_edge(
            record_node,
            entity_node,
            key="about",
            relation="about",
            timestamp=_timestamp(record.event_time),
        )
        if record.superseded_by is not None:
            graph.add_edge(
                record_node,
                _record_node(record.superseded_by),
                key="supersedes",
                relation="supersedes",
                timestamp=_timestamp(record.ingest_time),
            )
        raw_event = db.get(RawEvent, record.raw_event_id)
        if raw_event is not None:
            raw_node = f"raw_event:{raw_event.id}"
            graph.add_node(
                raw_node,
                kind="raw_event",
                id=str(raw_event.id),
                source_event_id=raw_event.source_event_id,
            )
            graph.add_edge(
                record_node,
                raw_node,
                key="derived_from",
                relation="derived_from",
                timestamp=_timestamp(raw_event.ingest_time),
            )

    for source in sources.values():
        graph.nodes[_source_node(source.id)].update(
            {"name": source.name, "source_type": source.source_type}
        )

    claim_query = select(Claim)
    if record_ids:
        claim_query = claim_query.where(Claim.record_id.in_(record_ids))
    else:
        return graph
    for claim in db.scalars(claim_query):
        claim_node = _claim_node(claim.id)
        edge_endpoint_ids.add(str(claim.id))
        edge_endpoint_ids.add(str(claim.record_id))
        edge_endpoint_ids.add(str(claim.source_id))
        graph.add_node(
            claim_node,
            kind="claim",
            id=str(claim.id),
            record_id=str(claim.record_id),
            attribute=claim.attribute,
            value=claim.value,
            source_id=str(claim.source_id),
            observed_at=_timestamp(claim.observed_at),
        )
        graph.add_edge(
            claim_node,
            _record_node(claim.record_id),
            key="about",
            relation="about",
            timestamp=_timestamp(claim.observed_at),
        )
        source_node = _source_node(claim.source_id)
        if source_node not in graph:
            graph.add_node(source_node, kind="source", id=str(claim.source_id))
        graph.add_edge(
            source_node,
            claim_node,
            key="asserted_by",
            relation="asserted_by",
            timestamp=_timestamp(claim.observed_at),
        )
        if claim.superseded_by is not None:
            graph.add_edge(
                claim_node,
                _claim_node(claim.superseded_by),
                key="supersedes",
                relation="supersedes",
                timestamp=_timestamp(claim.observed_at),
            )

    for edge in db.scalars(select(EvidenceEdge)):
        if (
            entity_ids is not None
            and not {
                str(edge.from_id),
                str(edge.to_id),
            }
            <= edge_endpoint_ids
        ):
            continue
        from_node = f"node:{edge.from_id}"
        to_node = f"node:{edge.to_id}"
        graph.add_node(from_node, kind="evidence_node", id=str(edge.from_id))
        graph.add_node(to_node, kind="evidence_node", id=str(edge.to_id))
        graph.add_edge(
            from_node,
            to_node,
            key=edge.relation,
            relation=edge.relation,
            timestamp=_timestamp(edge.timestamp),
        )
    return graph


def neighbours(g: nx.MultiDiGraph, node_id: str, depth: int = 2) -> nx.MultiDiGraph:
    """Return a copy of the graph neighborhood within an edge depth.

    Args:
        g: Evidence graph to inspect.
        node_id: Root node id.
        depth: Maximum number of traversed edges in either direction.

    Returns:
        A multigraph containing the root and reachable neighbors up to depth.

    Raises:
        ValueError: If depth is negative.
    """
    if depth < 0:
        raise ValueError("depth must not be negative")
    if node_id not in g:
        return nx.MultiDiGraph()
    visited = {node_id}
    frontier = {node_id}
    for _ in range(depth):
        adjacent = {
            neighbor
            for node in frontier
            for neighbor in set(g.successors(node)) | set(g.predecessors(node))
        }
        frontier = adjacent - visited
        visited.update(frontier)
    return g.subgraph(visited).copy()
