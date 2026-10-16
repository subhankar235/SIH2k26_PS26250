"""Tests for version diffs, schedule comparison, and impact analysis."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import networkx as nx
import pytest

from backend.app.core.enums import ScheduleStatus
from backend.app.core.exceptions import RequestValidationFailed
from backend.app.db.models.schedule import Schedule
from backend.app.schemas.replanning import ScheduleDiff
from backend.app.schemas.validity import ChangeEvent, InputRef
from backend.app.services.replanning.diff_inputs import diff_inputs
from backend.app.services.replanning.impact_analysis import impacted_assignments
from backend.app.services.replanning.schedule_diff import diff, stability


def _schedule(assignments: list[dict[str, object]]) -> Schedule:
    """Build a transient schedule fixture for assignment-only operations."""
    return Schedule(
        id=uuid4(),
        version=1,
        created_at=datetime.now(UTC),
        assignments=assignments,
        objectives={},
        solver_meta={},
        status=ScheduleStatus.VERIFIED.value,
        problem_hash="schedule-problem",
    )


def test_diff_inputs_reports_added_and_incremented_refs_deterministically() -> None:
    """Report changed versions by identity, independent of caller mapping keys."""
    input_id = uuid4()
    added_id = uuid4()
    old = {"arbitrary-a": InputRef(input_type="record", input_id=input_id, input_version=2)}
    new = {
        "different-key": InputRef(input_type="record", input_id=input_id, input_version=3),
        "added": InputRef(input_type="forecast", input_id=added_id, input_version=1),
    }

    events = diff_inputs(old, new)

    assert [(event.old_version, event.new_version) for event in events] == [(None, 1), (2, 3)]
    assert [event.input_type for event in events] == ["forecast", "record"]


def test_diff_inputs_rejects_physical_removal_without_tombstone() -> None:
    """Reject input removal because change events require a positive new version."""
    old_id = uuid4()
    old = {"record": InputRef(input_type="record", input_id=old_id, input_version=1)}

    with pytest.raises(RequestValidationFailed, match="tombstone"):
        diff_inputs(old, {})


def test_schedule_diff_classifies_changes_and_computes_stability() -> None:
    """Count unchanged tasks and return detailed added/removed/moved assignments."""
    old = _schedule(
        [
            {"task_id": "same", "resource_id": "crew-a", "start": 0, "end": 2},
            {"task_id": "move", "resource_id": "crew-a", "start": 2, "end": 3},
            {"task_id": "remove", "resource_id": "crew-b", "start": 0, "end": 1},
        ]
    )
    new = _schedule(
        [
            {"task_id": "same", "resource_id": "crew-a", "start": 0, "end": 2},
            {"task_id": "move", "resource_id": "crew-b", "start": 1, "end": 2},
            {"task_id": "add", "resource_id": "crew-a", "start": 3, "end": 4},
        ]
    )

    result = diff(old, new)

    assert result.unchanged == 1
    assert [item["task_id"] for item in result.added] == ["add"]
    assert [item["task_id"] for item in result.removed] == ["remove"]
    moved = [
        (item.task_id, item.before["resource_id"], item.after["resource_id"])
        for item in result.moved
    ]
    assert moved == [("move", "crew-a", "crew-b")]
    assert stability(result) == pytest.approx(1 / 3)
    assert stability(ScheduleDiff(added=[], removed=[], moved=[], unchanged=0)) == 1.0


def test_impact_analysis_uses_f3_paths_and_task_provenance() -> None:
    """Mark only tasks linked to the changed input and preserve independent work."""
    input_id = uuid4()
    decision_id = uuid4()
    schedule = _schedule(
        [
            {"task_id": "affected", "resource_id": "crew-a", "start": 0, "end": 1},
            {"task_id": "untouched", "resource_id": "crew-a", "start": 1, "end": 2},
        ]
    )
    schedule.solver_meta = {
        "problem": {
            "tasks": [
                {"id": "affected", "resource_type": "crew"},
                {"id": "untouched", "resource_type": "crew"},
            ],
            "resources": [{"id": "crew-a", "type": "crew"}],
        },
        "input_assignment_map": {str(input_id): {"task_ids": ["affected"], "resource_ids": []}},
    }
    graph = nx.DiGraph()
    input_node = f"input:record:{input_id}:v1"
    decision_node = f"decision:{decision_id}"
    graph.add_node(
        input_node,
        kind="input",
        input_type="record",
        input_id=input_id,
        input_version=1,
    )
    graph.add_node(
        decision_node,
        kind="decision",
        decision_id=decision_id,
        decision_type="schedule",
        ref_id=schedule.id,
    )
    graph.add_edge(input_node, decision_node)

    result = impacted_assignments(
        schedule,
        [ChangeEvent(input_type="record", input_id=input_id, old_version=1, new_version=2)],
        graph,
    )

    assert result.task_ids == frozenset({"affected"})
    assert [item["task_id"] for item in result.unaffected_assignments] == ["untouched"]
    assert result.decision_ids == frozenset({decision_id})
    assert result.requires_full_solve is False
