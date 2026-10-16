"""Incrementally invalidate decisions after versioned input changes."""

from __future__ import annotations

from uuid import UUID

import networkx as nx  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.enums import ValidityStatus
from backend.app.core.exceptions import RequestValidationFailed
from backend.app.db.models.decision import Decision, Dependency
from backend.app.schemas.validity import (
    ChangeEvent,
    DecisionState,
    InputRef,
    ReverifyOut,
    StatusChange,
)
from backend.app.services.validity.dependency_graph import (
    affected_decisions,
    build,
    descendants_only,
)
from backend.app.services.validity.input_versions import (
    current_input_version,
    input_lineage_ids,
)
from backend.app.services.validity.status import transition


def _current_version(db: Session, input_type: str, input_id: UUID) -> int | None:
    """Resolve the latest known version for a supported input row."""
    return current_input_version(db, input_type, input_id)


def _nodes_touched(g: nx.DiGraph, changed_inputs: list[InputRef]) -> int:
    """Count changed input, assumption, and decision nodes reached incrementally."""
    touched: set[str] = set()
    for node, attributes in g.nodes(data=True):
        if attributes.get("kind") != "input":
            continue
        for changed in changed_inputs:
            if (
                attributes.get("input_type") == changed.input_type
                and attributes.get("input_id") == changed.input_id
                and attributes.get("input_version") != changed.input_version
            ):
                touched.add(node)
                touched.update(descendants_only(g, node))
    return len(touched)


def _apply_reverification(
    db: Session,
    graph: nx.DiGraph,
    changed_inputs: list[InputRef],
    full_graph: bool = False,
) -> ReverifyOut:
    """Mark affected nonterminal decisions stale and summarize transitions."""
    affected = affected_decisions(graph, changed_inputs)
    changes: list[StatusChange] = []
    states: list[DecisionState] = []
    invalidated: list[UUID] = []
    with db.begin_nested():
        for decision_id in sorted(affected, key=str):
            decision = db.get(Decision, decision_id)
            if decision is None:
                continue
            old_status = ValidityStatus(decision.status)
            if old_status == ValidityStatus.INVALIDATED:
                invalidated.append(decision_id)
                states.append(
                    DecisionState(
                        decision_id=decision_id,
                        status=old_status,
                        eligible_for_reverification=False,
                    )
                )
                continue
            if old_status != ValidityStatus.STALE:
                transition(
                    db,
                    decision,
                    ValidityStatus.STALE,
                    reason="A dependent input version changed",
                    actor="reverification",
                )
                changes.append(
                    StatusChange(
                        decision_id=decision.id,
                        old_status=old_status,
                        new_status=ValidityStatus.STALE,
                    )
                )
            states.append(
                DecisionState(
                    decision_id=decision_id,
                    status=ValidityStatus.STALE,
                    eligible_for_reverification=True,
                )
            )
    return ReverifyOut(
        affected=sorted(affected, key=str),
        status_changes=changes,
        nodes_touched=len(graph) if full_graph else _nodes_touched(graph, changed_inputs),
        decision_states=states,
        skipped_invalidated=invalidated,
    )


def reverify(db: Session, change_events: list[ChangeEvent]) -> ReverifyOut:
    """Incrementally stale decisions that depend on changed input versions.

    Args:
        db: Active synchronous database session.
        change_events: Changed input ids with their new versions.

    Returns:
        Affected decision ids, status changes, and graph nodes touched.

    Raises:
        RequestValidationFailed: If a changed input does not have a strictly newer version.
        ValueError: If persisted input lineage contains a cycle.
        SQLAlchemyError: If graph state or status changes cannot be queried/persisted.
    """
    if not change_events:
        return ReverifyOut(affected=[], status_changes=[], nodes_touched=0)
    refs_by_key: dict[tuple[str, UUID], InputRef] = {}
    for event in change_events:
        if event.old_version is not None and event.new_version <= event.old_version:
            raise RequestValidationFailed(
                "Changed input version must increase",
                {"input_id": str(event.input_id), "old_version": event.old_version},
            )
        current_version = current_input_version(db, event.input_type, event.input_id)
        if current_version is None:
            raise RequestValidationFailed(
                "Changed input does not identify a supported persisted input",
                {"input_type": event.input_type, "input_id": str(event.input_id)},
            )
        if current_version != event.new_version:
            raise RequestValidationFailed(
                "Changed input version does not match persisted current version",
                {
                    "input_type": event.input_type,
                    "input_id": str(event.input_id),
                    "provided_version": event.new_version,
                    "current_version": current_version,
                },
            )
        lineage_ids = input_lineage_ids(db, event.input_type, event.input_id)
        if not lineage_ids:
            lineage_ids = {event.input_id}
        for input_id in lineage_ids:
            input_types = set(
                db.scalars(
                    select(Dependency.input_type).where(Dependency.input_id == input_id).distinct()
                ).all()
            ) or {event.input_type}
            for input_type in input_types:
                key = (input_type, input_id)
                existing = refs_by_key.get(key)
                if existing is None or event.new_version > existing.input_version:
                    refs_by_key[key] = InputRef(
                        input_type=input_type,
                        input_id=input_id,
                        input_version=event.new_version,
                    )
    changed_inputs = sorted(
        refs_by_key.values(),
        key=lambda ref: (ref.input_type, str(ref.input_id)),
    )
    return _apply_reverification(db, build(db, changed_inputs), changed_inputs)


def reverify_full(db: Session) -> ReverifyOut:
    """Recompute all stale decision statuses from current persisted input versions.

    Args:
        db: Active synchronous database session.

    Returns:
        The full-recompute result, structurally comparable to incremental reverify.

    Raises:
        ValueError: If a record input has a supersession cycle.
        SQLAlchemyError: If dependencies or decisions cannot be queried/persisted.
    """
    changed_inputs_by_key: dict[tuple[str, UUID], InputRef] = {}
    dependencies = db.scalars(select(Dependency)).all()
    for dependency in dependencies:
        current_version = _current_version(db, dependency.input_type, dependency.input_id)
        if current_version is None or current_version == dependency.input_version:
            continue
        ref = InputRef(
            input_type=dependency.input_type,
            input_id=dependency.input_id,
            input_version=current_version,
        )
        changed_inputs_by_key[(ref.input_type, ref.input_id)] = ref
    changed_inputs = sorted(
        changed_inputs_by_key.values(),
        key=lambda ref: (ref.input_type, str(ref.input_id)),
    )
    graph = build(db)
    return _apply_reverification(db, graph, changed_inputs, full_graph=True)
