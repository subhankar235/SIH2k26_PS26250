"""Compare persisted planning candidates using their objective values."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.schedule import Schedule
from backend.app.schemas.planning import Alternative, AlternativesOut, ScheduleOut


def list_alternatives(db: Session) -> AlternativesOut:
    """Return feasible verified/draft candidates and Pareto-optimal markers."""
    schedules = list(
        db.scalars(
            select(Schedule)
            .where(Schedule.status.in_(("draft", "verified", "approved")))
            .order_by(Schedule.id)
        ).all()
    )
    objective_names = sorted(
        {
            name
            for schedule in schedules
            for name in schedule.objectives
            if isinstance(schedule.objectives.get(name), (int, float))
        }
    )
    alternatives = []
    for candidate in schedules:
        candidate_values = candidate.objectives
        dominated = any(
            other.id != candidate.id
            and all(
                other.objectives.get(name, float("inf")) <= candidate_values.get(name, float("inf"))
                for name in objective_names
            )
            and any(
                other.objectives.get(name, float("inf")) < candidate_values.get(name, float("inf"))
                for name in objective_names
            )
            for other in schedules
        )
        alternatives.append(
            Alternative(
                schedule=ScheduleOut.model_validate(candidate),
                pareto_optimal=not dominated,
            )
        )
    return AlternativesOut(alternatives=alternatives, objective_names=objective_names)
