"""Generate deterministic synthetic crew records."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from data.generators._common import timestamp_at, validate_count, validate_seed

_SKILLS = ("repair", "inspection", "electrical", "mechanical", "safety")
_REGIONS = ("north", "south", "east", "west")


def generate(n: int, seed: int) -> pd.DataFrame:
    """Create ``n`` reproducible, synthetic crew members and skills."""
    validate_count(n, "n")
    validate_seed(seed)
    rng = np.random.default_rng(seed)
    rows = []
    for index in range(n):
        skills = sorted(
            rng.choice(_SKILLS, size=int(rng.integers(1, 4)), replace=False).tolist()
        )
        crew_id = f"crew-{seed}-{index:06d}"
        rows.append(
            {
                "record_id": f"record-crew-{seed}-{index:06d}",
                "entity_id": crew_id,
                "crew_id": crew_id,
                "source_id": f"source-crew-{index % 3}",
                "name": f"Synthetic Crew {index:04d}",
                "skills": json.dumps(skills, separators=(",", ":")),
                "available_hours": round(float(rng.uniform(20.0, 60.0)), 2),
                "region": _REGIONS[index % len(_REGIONS)],
                "event_time": timestamp_at(int(rng.integers(0, 24 * 365))),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "record_id",
            "entity_id",
            "crew_id",
            "source_id",
            "name",
            "skills",
            "available_hours",
            "region",
            "event_time",
        ],
    )
