"""Pareto comparison for persisted schedule alternatives."""

from __future__ import annotations

import math
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.enums import ScheduleStatus
from backend.app.db.models.schedule import Schedule
from backend.app.schemas.planning import Alternative, AlternativesOut, ScheduleOut


def _is_dominated(candidate: Schedule, schedules: Sequence[Schedule], names: list[str]) -> bool:
    """Return whether another schedule is no worse in all metrics and better in one."""
    candidate_values = {name: float(candidate.objectives[name]) for name in names}
    for other in schedules:
        if other.id == candidate.id:
            continue
        other_values = {name: float(other.objectives[name]) for name in names}
        if all(other_values[name] <= candidate_values[name] for name in names) and any(
            other_values[name] < candidate_values[name] for name in names
        ):
            return True
    return False


def compare(schedules: list[Schedule]) -> AlternativesOut:
    """Mark the Pareto frontier under minimization of persisted schedule objectives.

    Args:
        schedules: Candidate schedule rows.

    Returns:
        Objective names and each schedule with its Pareto-optimal flag.

    Raises:
        ValueError: If objective values are missing, non-numeric, or non-finite.
    """
    objective_names = sorted({name for schedule in schedules for name in schedule.objectives})
    for schedule in schedules:
        for name in objective_names:
            if name not in schedule.objectives:
                raise ValueError(f"schedule {schedule.id} lacks objective {name!r}")
            try:
                value = float(schedule.objectives[name])
            except (TypeError, ValueError) as error:
                raise ValueError(f"objective {name!r} must be numeric") from error
            if not math.isfinite(value):
                raise ValueError(f"objective {name!r} must be finite")

    return AlternativesOut(
        alternatives=[
            Alternative(
                schedule=ScheduleOut.model_validate(schedule),
                pareto_optimal=not _is_dominated(schedule, schedules, objective_names),
            )
            for schedule in sorted(
                schedules, key=lambda item: (item.problem_hash, item.version, str(item.id))
            )
        ],
        objective_names=objective_names,
    )


def list_alternatives(db: Session) -> AlternativesOut:
    """Load non-superseded schedule alternatives and compute their Pareto frontier.

    Args:
        db: Active synchronous database session.

    Returns:
        All non-superseded alternatives and their Pareto flags.
    """
    schedules = list(
        db.scalars(
            select(Schedule)
            .where(
                Schedule.status.not_in(
                    [
                        ScheduleStatus.INVALID.value,
                        ScheduleStatus.REJECTED.value,
                        ScheduleStatus.SUPERSEDED.value,
                    ]
                )
            )
            .order_by(Schedule.created_at, Schedule.id)
        ).all()
    )
    return compare(schedules)
