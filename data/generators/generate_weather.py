"""Generate deterministic synthetic daily regional weather observations."""

from __future__ import annotations

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from data.generators._common import timestamp_at, validate_count, validate_seed

_REGIONS = ("north", "south", "east", "west")


def generate(horizon_days: int, seed: int) -> pd.DataFrame:
    """Generate four synthetic weather series over the requested number of days."""
    validate_count(horizon_days, "horizon_days", minimum=1)
    validate_seed(seed)
    rng = np.random.default_rng(seed)
    rows = []
    for day in range(horizon_days):
        for region_index, region in enumerate(_REGIONS):
            hour = day * 24 + 12
            rows.append(
                {
                    "record_id": f"record-weather-{seed}-{day:04d}-{region_index}",
                    "entity_id": f"weather:{region}",
                    "source_id": f"source-weather-{region_index % 2}",
                    "region": region,
                    "temperature_c": round(float(rng.normal(16 + region_index * 3, 8)), 2),
                    "wind_speed_mps": round(float(rng.gamma(2.2, 3.0)), 2),
                    "precipitation_mm": round(float(rng.exponential(1.4)), 2),
                    "event_time": timestamp_at(hour),
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "record_id",
            "entity_id",
            "source_id",
            "region",
            "temperature_c",
            "wind_speed_mps",
            "precipitation_mm",
            "event_time",
        ],
    )
