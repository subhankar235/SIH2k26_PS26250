"""Generate synthetic resource/crew availability windows."""

from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from data.generators._common import timestamp_at, validate_count, validate_seed


def generate(
    resources: pd.DataFrame,
    crew: pd.DataFrame,
    horizon_days: int,
    seed: int,
) -> pd.DataFrame:
    """Create seeded daily availability windows for resource/crew pairings.

    Resources and crew are consumed read-only. For each day, each resource is
    assigned a rotating crew where available.
    """
    validate_count(horizon_days, "horizon_days", minimum=1)
    validate_seed(seed)
    required_resource = {"resource_id", "region"}
    required_crew = {"crew_id"}
    if not required_resource <= set(resources.columns):
        raise ValueError("resources must contain resource_id and region columns")
    if not required_crew <= set(crew.columns):
        raise ValueError("crew must contain a crew_id column")
    rng = np.random.default_rng(seed)
    resource_rows = resources.reset_index(drop=True).to_dict(orient="records")
    crew_rows = crew.reset_index(drop=True).to_dict(orient="records")
    rows: list[dict[str, object]] = []
    if resource_rows and crew_rows:
        for day in range(horizon_days):
            for index, resource in enumerate(resource_rows):
                selected_crew = crew_rows[(index + day) % len(crew_rows)]
                start_hour = int(rng.integers(6, 10))
                duration = int(rng.integers(6, 13))
                start = day * 24 + start_hour
                rows.append(
                    {
                        "record_id": f"record-availability-{seed}-{len(rows):06d}",
                        "entity_id": str(resource["resource_id"]),
                        "resource_id": str(resource["resource_id"]),
                        "crew_id": str(selected_crew["crew_id"]),
                        "region": str(resource["region"]),
                        "available": True,
                        "start_time": timestamp_at(start),
                        "end_time": timestamp_at(start + duration),
                        "event_time": timestamp_at(start),
                    }
                )
    return pd.DataFrame(
        rows,
        columns=[
            "record_id",
            "entity_id",
            "resource_id",
            "crew_id",
            "region",
            "available",
            "start_time",
            "end_time",
            "event_time",
        ],
    )
