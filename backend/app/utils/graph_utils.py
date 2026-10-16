"""JSON-safe graph serialization and bounded undirected-depth neighborhoods."""

from __future__ import annotations

import json
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

import networkx as nx  # type: ignore[import-untyped]


def _json_default(value: object) -> object:
    """Serialize common graph attribute objects for API and UI responses."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    raise TypeError(f"Graph value {type(value).__name__} is not JSON serializable")


def to_node_link(g: nx.Graph) -> dict[str, Any]:
    """Return a deterministic, JSON-safe NetworkX node-link representation.

    Uses the modern ``edges`` key consistently for Graph, DiGraph, MultiGraph,
    and MultiDiGraph instances.
    """
    try:
        data = nx.node_link_data(g, edges="edges")
    except TypeError:  # NetworkX 3.2-3.3 used the ``link`` keyword.
        data = nx.node_link_data(g)
        if "links" in data:
            data["edges"] = data.pop("links")
    data["nodes"] = sorted(data["nodes"], key=lambda node: str(node.get("id", "")))
    data["edges"] = sorted(
        data["edges"],
        key=lambda edge: (
            str(edge.get("source", "")),
            str(edge.get("target", "")),
            str(edge.get("key", "")),
        ),
    )
    encoded = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_json_default,
    )
    result = json.loads(encoded)
    if not isinstance(result, dict):
        raise TypeError("NetworkX node-link encoding did not produce an object")
    return result


def subgraph_by_depth(g: nx.Graph, root: str, depth: int) -> nx.Graph:
    """Copy nodes reachable within ``depth`` edges of ``root``.

    Directed graphs traverse incoming and outgoing edges, matching an undirected
    neighborhood. Depth zero returns the root only; unknown roots return an empty
    graph of the same graph class.

    Raises:
        TypeError: If depth is not an integer or is a boolean.
        ValueError: If depth is negative.
    """
    if not isinstance(depth, int) or isinstance(depth, bool):
        raise TypeError("depth must be an integer")
    if depth < 0:
        raise ValueError("depth must not be negative")
    if root not in g:
        empty = g.__class__()
        empty.graph.update(g.graph)
        return empty

    visited = {root}
    frontier = {root}
    for _ in range(depth):
        adjacent: set[str] = set()
        for node in frontier:
            if g.is_directed():
                adjacent.update(g.successors(node))
                adjacent.update(g.predecessors(node))
            else:
                adjacent.update(g.neighbors(node))
        frontier = adjacent - visited
        visited.update(frontier)
        if not frontier:
            break
    return g.subgraph(visited).copy()
