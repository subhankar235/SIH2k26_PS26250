"""Build and traverse the decision input-version dependency graph."""

from __future__ import annotations

from uuid import UUID

import networkx as nx  # type: ignore[import-untyped]
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from backend.app.db.models.decision import Assumption, Decision, Dependency
from backend.app.schemas.validity import InputRef


def _input_node(input_type: str, input_id: UUID, version: int) -> str:
    """Create a stable graph key for one input version."""
    return f"input:{input_type}:{input_id}:v{version}"


def build(db: Session, input_filter: list[InputRef] | None = None) -> nx.DiGraph:
    """Build the graph from input versions through assumptions to decisions.

    Args:
        db: Active synchronous database session.
        input_filter: Optional changed inputs; restrict construction to their downstream decisions.

    Returns:
        Directed graph with input, assumption, and decision node metadata.

    Raises:
        SQLAlchemyError: If persisted dependency data cannot be queried.
    """
    graph = nx.DiGraph()
    if input_filter == []:
        return graph
    dependency_query = select(Dependency)
    if input_filter is not None:
        predicates = [
            and_(Dependency.input_type == item.input_type, Dependency.input_id == item.input_id)
            for item in input_filter
        ]
        matching_dependencies = db.scalars(
            dependency_query.where(or_(*predicates)).order_by(Dependency.id)
        ).all()
        decision_ids = {item.decision_id for item in matching_dependencies}
        if not decision_ids:
            return graph
        decisions = db.scalars(
            select(Decision).where(Decision.id.in_(decision_ids)).order_by(Decision.id)
        ).all()
        assumptions = db.scalars(
            select(Assumption)
            .where(Assumption.decision_id.in_(decision_ids))
            .order_by(Assumption.id)
        ).all()
        dependencies = db.scalars(
            dependency_query.where(Dependency.decision_id.in_(decision_ids)).order_by(Dependency.id)
        ).all()
    else:
        decisions = db.scalars(select(Decision).order_by(Decision.id)).all()
        assumptions = db.scalars(select(Assumption).order_by(Assumption.id)).all()
        dependencies = db.scalars(dependency_query.order_by(Dependency.id)).all()
    assumptions_by_decision: dict[UUID, list[Assumption]] = {}
    dependencies_by_decision: dict[UUID, list[Dependency]] = {}
    for assumption in assumptions:
        assumptions_by_decision.setdefault(assumption.decision_id, []).append(assumption)
    for dependency in dependencies:
        if dependency.input_version < 1:
            continue
        dependencies_by_decision.setdefault(dependency.decision_id, []).append(dependency)

    for decision in decisions:
        decision_node = f"decision:{decision.id}"
        graph.add_node(
            decision_node,
            kind="decision",
            decision_id=decision.id,
            decision_type=decision.decision_type,
            ref_id=decision.ref_id,
            version=decision.version,
            status=decision.status,
        )
        assumption_nodes: list[str] = []
        for assumption in assumptions_by_decision.get(decision.id, []):
            assumption_node = f"assumption:{assumption.id}"
            graph.add_node(
                assumption_node,
                kind="assumption",
                assumption_id=assumption.id,
                decision_id=decision.id,
            )
            graph.add_edge(assumption_node, decision_node)
            assumption_nodes.append(assumption_node)

        for dependency in dependencies_by_decision.get(decision.id, []):
            input_node = _input_node(
                dependency.input_type,
                dependency.input_id,
                dependency.input_version,
            )
            graph.add_node(
                input_node,
                kind="input",
                input_type=dependency.input_type,
                input_id=dependency.input_id,
                input_version=dependency.input_version,
            )
            if assumption_nodes:
                graph.add_edges_from(
                    (input_node, assumption_node) for assumption_node in assumption_nodes
                )
            else:
                graph.add_edge(input_node, decision_node)
    return graph


def descendants_only(g: nx.DiGraph, node: str) -> set[str]:
    """Return all descendants of a graph node excluding the node itself.

    Args:
        g: Directed decision dependency graph.
        node: Node id whose descendants are requested.

    Returns:
        Reachable descendants, or an empty set when node is absent.

    Raises:
        None.
    """
    if node not in g:
        return set()
    return set(nx.descendants(g, node))


def affected_decisions(g: nx.DiGraph, changed_inputs: list[InputRef]) -> set[UUID]:
    """Find decisions dependent on an input whose version has changed.

    Args:
        g: Directed decision dependency graph.
        changed_inputs: Current versions of changed inputs.

    Returns:
        UUIDs of decisions with dependencies on an older input version.

    Raises:
        None.
    """
    affected: set[UUID] = set()
    changed_keys: dict[tuple[str, UUID], int] = {}
    for item in changed_inputs:
        key = (item.input_type, item.input_id)
        changed_keys[key] = max(changed_keys.get(key, 0), item.input_version)
    for node, attributes in g.nodes(data=True):
        if attributes.get("kind") != "input":
            continue
        input_type = attributes.get("input_type")
        input_id = attributes.get("input_id")
        input_version = attributes.get("input_version")
        if not isinstance(input_type, str) or not isinstance(input_id, UUID):
            continue
        if not isinstance(input_version, int) or input_version < 1:
            continue
        key = (input_type, input_id)
        new_version = changed_keys.get(key)
        if new_version is None or new_version <= input_version:
            continue
        for descendant in descendants_only(g, node):
            decision_node = g.nodes[descendant]
            decision_id = decision_node.get("decision_id")
            if decision_node.get("kind") == "decision" and isinstance(decision_id, UUID):
                affected.add(decision_id)
    return affected
