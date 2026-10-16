"""Contract tests for UTC, UUID/hash, and graph serialization helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import networkx as nx
import pytest

from backend.app.utils.graph_utils import subgraph_by_depth, to_node_link
from backend.app.utils.ids import new_id, stable_hash
from backend.app.utils.time import parse_iso, utcnow


def test_utcnow_and_parse_iso_return_aware_utc_datetimes() -> None:
    """Normalize UTC, offset, Zulu, and naive ISO timestamps consistently."""
    current = utcnow()
    assert current.tzinfo is UTC
    assert abs((datetime.now(UTC) - current).total_seconds()) < 2
    assert parse_iso("2026-05-06T12:00:00Z") == datetime(2026, 5, 6, 12, tzinfo=UTC)
    assert parse_iso("2026-05-06T14:00:00+02:00") == datetime(2026, 5, 6, 12, tzinfo=UTC)
    assert parse_iso("2026-05-06T12:00:00") == datetime(2026, 5, 6, 12, tzinfo=UTC)
    with pytest.raises(ValueError, match="Invalid ISO"):
        parse_iso("not-a-timestamp")
    with pytest.raises(TypeError, match="must be a string"):
        parse_iso(datetime.now(UTC))  # type: ignore[arg-type]


def test_uuid_and_stable_hash_are_well_formed_and_canonical() -> None:
    """Produce unique UUIDs and hashes stable to mapping/set order."""
    first_id, second_id = new_id(), new_id()
    assert isinstance(first_id, UUID) and first_id != second_id
    left = {"b": [2, 3], "a": {"right", "left"}}
    right = {"a": {"left", "right"}, "b": [2, 3]}
    assert stable_hash(left) == stable_hash(right)
    assert len(stable_hash(left)) == 64
    with pytest.raises(ValueError):
        stable_hash({"not_json": float("nan")})


@pytest.mark.parametrize("graph_type", [nx.Graph, nx.DiGraph, nx.MultiGraph, nx.MultiDiGraph])
def test_graph_node_link_serialization_and_depth_subgraph(graph_type) -> None:
    """Keep graph type, parallel edges, JSON-safe attributes, and depth boundaries."""
    graph = graph_type()
    graph.graph["created_at"] = datetime(2026, 1, 1, tzinfo=UTC)
    graph.add_node("root", identifier=new_id())
    graph.add_node("one", count=1)
    graph.add_node("two", count=2)
    graph.add_node("far", count=3)
    graph.add_edge("root", "one", relation="next")
    if graph.is_multigraph():
        graph.add_edge("root", "one", relation="parallel")
    graph.add_edge("one", "two", relation="next")
    graph.add_edge("two", "far", relation="next")

    shallow = subgraph_by_depth(graph, "root", 1)
    assert set(shallow) == {"root", "one"}
    assert shallow.number_of_edges() == (2 if graph.is_multigraph() else 1)
    assert set(subgraph_by_depth(graph, "root", 0)) == {"root"}
    assert subgraph_by_depth(graph, "missing", 2).number_of_nodes() == 0
    with pytest.raises(ValueError, match="negative"):
        subgraph_by_depth(graph, "root", -1)

    node_link = to_node_link(graph)
    assert node_link["directed"] is graph.is_directed()
    assert node_link["multigraph"] is graph.is_multigraph()
    assert node_link["edges"]
    round_tripped = nx.node_link_graph(node_link, edges="edges")
    assert set(round_tripped.nodes) == set(graph.nodes)
    assert round_tripped.number_of_edges() == graph.number_of_edges()
