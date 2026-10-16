"""Incremental reverification equivalence over seeded random change batches."""

from __future__ import annotations

import random
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from backend.app.core.enums import ValidityStatus
from backend.app.db.models import Decision, Dependency
from backend.app.schemas.validity import ChangeEvent
from backend.app.services.validity.reverifier import reverify, reverify_full


@pytest.mark.parametrize("seed", [3, 29, 1729])
def test_random_incremental_reverification_matches_full_status_recompute(
    db, source_factory, record_factory, seed: int
) -> None:
    """Compare the affected decision statuses from incremental and full traversals."""
    rng = random.Random(seed)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    old_rows = []
    current_rows = []
    selected = set(rng.sample(range(12), rng.randint(1, 12)))
    for index in range(12):
        source = source_factory(name=f"reverify-source-{index}")
        entity_id = f"resource:reverify-{index}"
        old = record_factory(
            entity_id=entity_id,
            source=source,
            version=1,
            event_time=now,
            payload={"entity_id": entity_id, "capacity_mw": 1},
        )
        if index in selected:
            current = record_factory(
                entity_id=entity_id,
                source=source,
                version=2,
                event_time=now,
                payload={"entity_id": entity_id, "capacity_mw": 2},
            )
            old.superseded_by = current.id
        else:
            current = old
        old_rows.append(old)
        current_rows.append(current)
    db.flush()

    decisions: list[Decision] = []
    for old in old_rows:
        decision = Decision(
            decision_type="schedule",
            status=ValidityStatus.VERIFIED.value,
            ref_id=old.id,
            version=1,
        )
        db.add(decision)
        db.flush()
        db.add(
            Dependency(
                decision_id=decision.id,
                input_type="record",
                input_id=old.id,
                input_version=1,
            )
        )
        decisions.append(decision)
    db.flush()

    events = [
        ChangeEvent(
            input_type="record",
            input_id=current_rows[index].id,
            old_version=1,
            new_version=2,
        )
        for index in sorted(selected)
    ]
    incremental = reverify(db, events)
    incremental_statuses = {row.id: row.status for row in db.scalars(select(Decision)).all()}

    for decision in decisions:
        decision.status = ValidityStatus.VERIFIED.value
        decision.version = 1
    db.flush()
    full = reverify_full(db)
    full_statuses = {row.id: row.status for row in db.scalars(select(Decision)).all()}

    assert set(incremental.affected) == set(full.affected)
    assert incremental_statuses == full_statuses
    assert {
        decision_id
        for decision_id, status in incremental_statuses.items()
        if status == ValidityStatus.STALE.value
    } == {decisions[index].id for index in selected}
