"""Generate deterministic synthetic resource records."""

from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from data.generators._common import timestamp_at, validate_count, validate_seed

_REGIONS = ("north", "south", "east", "west")
_RESOURCE_TYPES = ("solar", "wind", "hydro", "thermal", "storage")


def generate(n: int, seed: int) -> pd.DataFrame:
    """Create ``n`` synthetic resource records from a local seeded generator."""
    validate_count(n, "n")
    validate_seed(seed)
    rng = np.random.default_rng(seed)
    rows = []
    for index in range(n):
        resource_id = f"resource-{seed}-{index:06d}"
        resource_type = _RESOURCE_TYPES[int(rng.integers(0, len(_RESOURCE_TYPES)))]
        rows.append(
            {
                "record_id": f"record-resource-{seed}-{index:06d}",
                "entity_id": resource_id,
                "resource_id": resource_id,
                "source_id": f"source-resource-{index % 3}",
                "name": f"Synthetic {resource_type.title()} {index:04d}",
                "resource_type": resource_type,
                "capacity_mw": round(float(rng.uniform(5.0, 500.0)), 3),
                "region": _REGIONS[index % len(_REGIONS)],
                "event_time": timestamp_at(int(rng.integers(0, 24 * 365))),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "record_id",
            "entity_id",
            "resource_id",
            "source_id",
            "name",
            "resource_type",
            "capacity_mw",
            "region",
            "event_time",
        ],
    )
