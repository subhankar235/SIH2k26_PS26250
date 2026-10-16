"""Resolve current versions and lineage ids for supported decision inputs."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.enums import SourceType
from backend.app.db.models.forecast import Forecast
from backend.app.db.models.record import Record
from backend.app.db.models.schedule import Schedule


def record_lineage(db: Session, record_id: UUID, input_type: str) -> tuple[int, set[UUID]] | None:
    """Resolve the active record version and all predecessor ids for an input.

    Args:
        db: Active synchronous database session.
        record_id: Any record id in a supersession lineage.
        input_type: ``record`` or the corresponding source type alias.

    Returns:
        Latest version and all related record ids, or None for unsupported/missing input.

    Raises:
        ValueError: If persisted lineage contains a cycle or invalid cross-entity link.
    """
    record = db.get(Record, record_id)
    if record is None:
        return None
    if input_type != "record" and record.source_type != input_type:
        return None

    current = record
    root_entity = record.entity_id
    root_source = record.source_type
    forward_seen: set[UUID] = set()
    while current.superseded_by is not None:
        if current.id in forward_seen:
            raise ValueError("record supersession cycle detected")
        forward_seen.add(current.id)
        next_record = db.get(Record, current.superseded_by)
        if next_record is None:
            break
        if next_record.entity_id != root_entity or next_record.source_type != root_source:
            raise ValueError("record supersession link crosses entity or source types")
        current = next_record

    lineage_ids: set[UUID] = {current.id}
    frontier = [current.id]
    while frontier:
        newer_id = frontier.pop()
        predecessors = db.scalars(
            select(Record.id).where(Record.superseded_by == newer_id).order_by(Record.id)
        ).all()
        for predecessor_id in predecessors:
            if predecessor_id in lineage_ids:
                continue
            predecessor = db.get(Record, predecessor_id)
            if (
                predecessor is None
                or predecessor.entity_id != root_entity
                or predecessor.source_type != root_source
            ):
                continue
            lineage_ids.add(predecessor_id)
            frontier.append(predecessor_id)
    return current.version, lineage_ids


def current_input_version(db: Session, input_type: str, input_id: UUID) -> int | None:
    """Return the current version for a persisted decision input.

    Args:
        db: Active synchronous database session.
        input_type: Record/source, forecast, or schedule type.
        input_id: UUID of a version in the input lineage.

    Returns:
        Current logical version, or None if the input is missing or unsupported.

    Raises:
        ValueError: If persisted input lineage is malformed.
    """
    if input_type == "record" or input_type in {source.value for source in SourceType}:
        lineage = record_lineage(db, input_id, input_type)
        return lineage[0] if lineage is not None else None
    if input_type == "forecast":
        item = db.get(Forecast, input_id)
        if item is None:
            return None
        return db.scalar(
            select(Forecast.version)
            .where(Forecast.target == item.target)
            .order_by(Forecast.version.desc(), Forecast.created_at.desc(), Forecast.id)
            .limit(1)
        )
    if input_type == "schedule":
        lineage_ids = _schedule_lineage_ids(db, input_id)
        if not lineage_ids:
            return None
        return db.scalar(
            select(Schedule.version)
            .where(Schedule.id.in_(lineage_ids))
            .order_by(Schedule.version.desc(), Schedule.created_at.desc(), Schedule.id)
            .limit(1)
        )
    return None


def input_lineage_ids(db: Session, input_type: str, input_id: UUID) -> set[UUID]:
    """Return IDs whose dependencies should be invalidated by a newer input.

    Args:
        db: Active synchronous database session.
        input_type: Record/source, forecast, or schedule type.
        input_id: UUID of any input version in its lineage.

    Returns:
        IDs of all older/current versions in the logical lineage.

    Raises:
        ValueError: If a persisted lineage contains a cycle.
    """
    if input_type == "record" or input_type in {source.value for source in SourceType}:
        lineage = record_lineage(db, input_id, input_type)
        return lineage[1] if lineage is not None else set()
    if input_type == "forecast":
        item = db.get(Forecast, input_id)
        if item is None:
            return set()
        return set(db.scalars(select(Forecast.id).where(Forecast.target == item.target)).all())
    if input_type == "schedule":
        return _schedule_lineage_ids(db, input_id)
    return set()


def _schedule_lineage_ids(db: Session, schedule_id: UUID) -> set[UUID]:
    """Collect schedule ancestors and all descendants connected by parent ids."""
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        return set()
    related: set[UUID] = {schedule.id}
    cursor = schedule
    while cursor.parent_schedule_id is not None:
        if cursor.parent_schedule_id in related:
            raise ValueError("schedule parent cycle detected")
        parent = db.get(Schedule, cursor.parent_schedule_id)
        if parent is None:
            break
        related.add(parent.id)
        cursor = parent

    frontier = list(related)
    while frontier:
        children = db.scalars(
            select(Schedule.id)
            .where(Schedule.parent_schedule_id.in_(frontier))
            .order_by(Schedule.version, Schedule.id)
        ).all()
        frontier = [child_id for child_id in children if child_id not in related]
        related.update(frontier)
    return related
