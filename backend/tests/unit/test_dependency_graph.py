"""Dependency graph traversal correctness for changed versioned inputs."""

from __future__ import annotations

from uuid import uuid4

from backend.app.db.models import Assumption, Decision, Dependency
from backend.app.schemas.validity import InputRef
from backend.app.services.validity.dependency_graph import (
    affected_decisions,
    build,
    descendants_only,
)


def test_affected_decisions_follow_only_newer_input_dependency_paths(db) -> None:
    """Select downstream decisions for one newer ref, not unrelated/equal refs."""
    first_input, second_input = uuid4(), uuid4()
    first = Decision(decision_type="schedule", status="verified", ref_id=uuid4(), version=1)
    second = Decision(decision_type="forecast", status="verified", ref_id=uuid4(), version=1)
    db.add_all([first, second])
    db.flush()
    assumption = Assumption(decision_id=first.id, description="capacity is trusted", parameters={})
    db.add(assumption)
    db.add_all(
        [
            Dependency(
                decision_id=first.id,
                input_type="record",
                input_id=first_input,
                input_version=1,
            ),
            Dependency(
                decision_id=second.id,
                input_type="forecast",
                input_id=second_input,
                input_version=4,
            ),
        ]
    )
    db.flush()

    graph = build(db)
    changed = [InputRef(input_type="record", input_id=first_input, input_version=2)]
    assert affected_decisions(graph, changed) == {first.id}
    assert affected_decisions(
        graph,
        [InputRef(input_type="forecast", input_id=second_input, input_version=4)],
    ) == set()
    input_node = f"input:record:{first_input}:v1"
    assert descendants_only(graph, input_node) >= {
        f"assumption:{assumption.id}",
        f"decision:{first.id}",
    }
    assert descendants_only(graph, "missing") == set()
