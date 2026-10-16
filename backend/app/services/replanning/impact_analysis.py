"""Use F3 dependency paths and input-to-assignment provenance for impact analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import networkx as nx  # type: ignore[import-untyped]

from backend.app.db.models.schedule import Schedule
from backend.app.schemas.validity import ChangeEvent

_RECORD_TYPES = {"record", "resource", "crew", "availability", "weather", "constraint"}


@dataclass(frozen=True)
class ImpactSet:
    """Changed inputs, affected schedule assignments, and fallback requirement."""

    task_ids: frozenset[str]
    decision_ids: frozenset[UUID]
    assignments: tuple[dict[str, Any], ...]
    unaffected_assignments: tuple[dict[str, Any], ...]
    requires_full_solve: bool


def _same_input_type(left: object, right: object) -> bool:
    """Treat source-specific record types as aliases of generic record refs."""
    return left == right or (
        left in _RECORD_TYPES and right in _RECORD_TYPES and "record" in {left, right}
    )


def _assignments_for(schedule: Schedule) -> dict[str, dict[str, Any]]:
    """Index assignments for task-level impact calculation."""
    result: dict[str, dict[str, Any]] = {}
    for assignment in schedule.assignments:
        task_id = assignment.get("task_id")
        if isinstance(task_id, str) and task_id:
            result[task_id] = assignment
    return result


def impacted_assignments(
    schedule: Schedule,
    changes: list[ChangeEvent],
    g: nx.DiGraph,
) -> ImpactSet:
    """Find assignments downstream of changed inputs in the F3 dependency graph.

    Task-level provenance is read from ``solver_meta.input_assignment_map``. If
    provenance or a schedule decision node is absent, the analysis is conservative
    and requires a full solve rather than freezing potentially affected work.

    Args:
        schedule: Schedule whose work may need recomputation.
        changes: New input versions that triggered replanning.
        g: Input-version/assumption/decision dependency graph from F3.

    Returns:
        Affected task ids, assignments, downstream schedule decisions, and whether
        a full re-solve is required for correctness.
    """
    assignments = _assignments_for(schedule)
    decision_nodes = [
        node
        for node, attrs in g.nodes(data=True)
        if attrs.get("kind") == "decision"
        and attrs.get("decision_type") == "schedule"
        and attrs.get("ref_id") == schedule.id
    ]
    affected_decisions: set[UUID] = set()
    matching_changes: list[ChangeEvent] = []
    for change in changes:
        input_nodes = [
            node
            for node, attrs in g.nodes(data=True)
            if attrs.get("kind") == "input"
            and attrs.get("input_id") == change.input_id
            and _same_input_type(attrs.get("input_type"), change.input_type)
            and isinstance(attrs.get("input_version"), int)
            and attrs["input_version"] < change.new_version
        ]
        reaches_schedule = False
        for input_node in input_nodes:
            for descendant in nx.descendants(g, input_node):
                attrs = g.nodes[descendant]
                decision_id = attrs.get("decision_id")
                if attrs.get("kind") == "decision" and isinstance(decision_id, UUID):
                    affected_decisions.add(decision_id)
                if descendant in decision_nodes:
                    reaches_schedule = True
        if reaches_schedule:
            matching_changes.append(change)

    if not matching_changes or not decision_nodes:
        return ImpactSet(
            task_ids=frozenset(assignments),
            decision_ids=frozenset(affected_decisions),
            assignments=tuple(assignments[key] for key in sorted(assignments)),
            unaffected_assignments=(),
            requires_full_solve=True,
        )

    input_map = schedule.solver_meta.get("input_assignment_map", {})
    problem = schedule.solver_meta.get("problem", {})
    tasks = {
        str(task.get("id")): task
        for task in problem.get("tasks", [])
        if isinstance(task, dict) and task.get("id") is not None
    }
    resources = {
        str(resource.get("id")): resource
        for resource in problem.get("resources", [])
        if isinstance(resource, dict) and resource.get("id") is not None
    }
    impacted_ids: set[str] = set()
    requires_full_solve = not isinstance(input_map, dict) or not input_map
    for change in matching_changes:
        provenance = input_map.get(str(change.input_id)) if isinstance(input_map, dict) else None
        if not isinstance(provenance, dict):
            requires_full_solve = True
            impacted_ids.update(assignments)
            continue
        if provenance.get("global") is True:
            impacted_ids.update(assignments)
        impacted_ids.update(
            task_id
            for task_id in provenance.get("task_ids", [])
            if isinstance(task_id, str) and task_id in assignments
        )
        changed_resources = {
            str(resource_id)
            for resource_id in provenance.get("resource_ids", [])
            if str(resource_id) in resources
        }
        changed_types = {
            str(resources[resource_id].get("type", resources[resource_id].get("resource_type", "")))
            for resource_id in changed_resources
        }
        impacted_ids.update(
            task_id
            for task_id, task in tasks.items()
            if task_id in assignments
            and (
                task.get("resource_type") in changed_types
                or task.get("resource_type") in {"*", "any"}
            )
        )
        if (
            not provenance.get("global")
            and not provenance.get("task_ids")
            and not changed_resources
        ):
            requires_full_solve = True
            impacted_ids.update(assignments)

    # Unknown task ids in the schedule cannot be safely frozen.
    if set(assignments) - set(tasks):
        requires_full_solve = True
        impacted_ids.update(assignments)
    impacted_ids &= set(assignments)
    untouched = set(assignments) - impacted_ids
    if not impacted_ids and assignments:
        requires_full_solve = True
        impacted_ids.update(assignments)
        untouched.clear()
    return ImpactSet(
        task_ids=frozenset(impacted_ids),
        decision_ids=frozenset(affected_decisions),
        assignments=tuple(assignments[key] for key in sorted(impacted_ids)),
        unaffected_assignments=tuple(assignments[key] for key in sorted(untouched)),
        requires_full_solve=requires_full_solve,
    )
