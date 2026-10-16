"""Generate deterministic synthetic resource-capacity constraints."""

from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from data.generators._common import timestamp_at, validate_seed


def generate(resources: pd.DataFrame, seed: int) -> list[dict[str, object]]:
    """Create one synthetic operational limit per resource from a local RNG."""
    validate_seed(seed)
    if "resource_id" not in resources.columns or "capacity_mw" not in resources.columns:
        raise ValueError("resources must contain resource_id and capacity_mw columns")
    rng = np.random.default_rng(seed)
    constraints: list[dict[str, object]] = []
    for index, resource in enumerate(resources.to_dict(orient="records")):
        capacity = float(resource["capacity_mw"])
        ratio = float(rng.uniform(0.65, 1.0))
        constraints.append(
            {
                "record_id": f"record-constraint-{seed}-{index:06d}",
                "entity_id": str(resource["resource_id"]),
                "source_id": f"source-constraint-{index % 2}",
                "constraint_type": "max_capacity_mw",
                "limit_mw": round(capacity * ratio, 3),
                "active": True,
                "event_time": timestamp_at(index),
            }
        )
    return constraints
