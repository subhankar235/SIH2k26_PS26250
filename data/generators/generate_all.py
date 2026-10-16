"""Create a complete, seeded, synthetic raw dataset and fault-label parquet file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from data.generators._common import validate_count, validate_seed
from data.generators.generate_availability import generate as generate_availability
from data.generators.generate_constraints import generate as generate_constraints
from data.generators.generate_crew import generate as generate_crew
from data.generators.generate_resources import generate as generate_resources
from data.generators.generate_weather import generate as generate_weather

_LABEL_COLUMNS = [
    "record_id",
    "fault_type",
    "true_value",
    "duplicate_of",
    "conflict_group_id",
    "true_freshness_time",
]


def _label(
    record_id: str,
    fault_type: str,
    *,
    true_value: Any = None,
    duplicate_of: str | None = None,
    conflict_group_id: str | None = None,
    true_freshness_time: str | None = None,
) -> dict[str, Any]:
    """Build one row of ground-truth fault labels."""
    return {
        "record_id": record_id,
        "fault_type": fault_type,
        "true_value": json.dumps(true_value, sort_keys=True, separators=(",", ":"), default=str)
        if true_value is not None
        else None,
        "duplicate_of": duplicate_of,
        "conflict_group_id": conflict_group_id,
        "true_freshness_time": true_freshness_time,
    }


def _inject_synthetic_labels(
    resources: pd.DataFrame,
    crew: pd.DataFrame,
    availability: pd.DataFrame,
    weather: pd.DataFrame,
    constraints: list[dict[str, object]],
    seed: int,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    list[dict[str, object]],
    pd.DataFrame,
]:
    """Apply deterministic known faults while retaining exact ground truth."""
    rng = np.random.default_rng(seed + 7919)
    labels: list[dict[str, Any]] = []

    if not crew.empty:
        missing_crew_count = max(1, round(len(crew) * 0.02))
        missing_crew_ids = rng.choice(crew.index.to_numpy(), size=missing_crew_count, replace=False)
        for row_index in sorted(int(value) for value in missing_crew_ids):
            original = crew.loc[row_index, "skills"]
            crew.loc[row_index, "skills"] = None
            labels.append(
                _label(
                    str(crew.loc[row_index, "record_id"]),
                    "missing",
                    true_value=original,
                    true_freshness_time=str(crew.loc[row_index, "event_time"]),
                )
            )

    if not availability.empty:
        stale_count = max(1, round(len(availability) * 0.02))
        stale_indices = rng.choice(
            availability.index.to_numpy(), size=stale_count, replace=False
        )
        for index in sorted(int(value) for value in stale_indices):
            original_time = str(availability.loc[index, "event_time"])
            stale_time = pd.Timestamp(original_time) - pd.Timedelta(days=365)
            availability.loc[index, "event_time"] = stale_time.isoformat()
            labels.append(
                _label(
                    str(availability.loc[index, "record_id"]),
                    "stale",
                    true_value=original_time,
                    true_freshness_time=original_time,
                )
            )

    if not weather.empty:
        duplicate_count = max(1, round(len(weather) * 0.03))
        duplicate_indices = rng.choice(
            weather.index.to_numpy(), size=min(duplicate_count, len(weather)), replace=False
        )
        duplicates = []
        for index in sorted(int(value) for value in duplicate_indices):
            original = weather.loc[index].to_dict()
            duplicate = dict(original)
            duplicate_id = f"{original['record_id']}-duplicate"
            duplicate["record_id"] = duplicate_id
            duplicates.append(duplicate)
            labels.append(
                _label(
                    duplicate_id,
                    "duplicate",
                    true_value=original,
                    duplicate_of=str(original["record_id"]),
                    true_freshness_time=str(original["event_time"]),
                )
            )
        weather = pd.concat([weather, pd.DataFrame(duplicates)], ignore_index=True)

    if len(resources) >= 2:
        conflict_count = min(max(1, round(len(resources) * 0.02)), len(resources) // 2)
        candidates = rng.choice(resources.index.to_numpy(), size=conflict_count, replace=False)
        missing_count = max(1, round(len(resources) * 0.01))
        missing_candidates = [
            int(value) for value in resources.index if value not in set(candidates.tolist())
        ]
        missing_indices: list[int] = (
            [
                int(value)
                for value in rng.choice(
                    missing_candidates,
                    size=min(missing_count, len(missing_candidates)),
                    replace=False,
                ).tolist()
            ]
            if missing_candidates
            else []
        )
        for index in sorted(missing_indices):
            original_value = float(str(resources.loc[index, "capacity_mw"]))
            labels.append(
                _label(
                    str(resources.loc[index, "record_id"]),
                    "missing",
                    true_value=original_value,
                    true_freshness_time=str(resources.loc[index, "event_time"]),
                )
            )
            resources.loc[index, "capacity_mw"] = np.nan

        conflict_rows = []
        for conflict_number, chosen_index in enumerate(sorted(int(value) for value in candidates)):
            first = resources.loc[chosen_index]
            true_capacity = float(str(first["capacity_mw"]))
            conflict_group = f"conflict-{seed}-resource-{conflict_number:05d}"
            second = first.to_dict()
            second["record_id"] = f"record-resource-conflict-{seed}-{conflict_number:05d}"
            second["source_id"] = f"source-resource-conflict-{conflict_number % 5}"
            second["capacity_mw"] = round(true_capacity + float(rng.uniform(5, 50)), 3)
            conflict_rows.append(second)
            labels.append(
                _label(
                    str(first["record_id"]),
                    "conflicting",
                    true_value=true_capacity,
                    conflict_group_id=conflict_group,
                    true_freshness_time=str(first["event_time"]),
                )
            )
            labels.append(
                _label(
                    str(second["record_id"]),
                    "conflicting",
                    true_value=true_capacity,
                    conflict_group_id=conflict_group,
                    true_freshness_time=str(second["event_time"]),
                )
            )
        resources = pd.concat([resources, pd.DataFrame(conflict_rows)], ignore_index=True)

    if constraints:
        changed_count = max(1, round(len(constraints) * 0.02))
        changed_indices = rng.choice(
            len(constraints), size=min(changed_count, len(constraints)), replace=False
        )
        for index in sorted(int(value) for value in changed_indices):
            constraint = constraints[index]
            true_limit = float(str(constraint["limit_mw"]))
            constraint["limit_mw"] = round(true_limit * 0.5, 3)
            labels.append(
                _label(
                    str(constraint["record_id"]),
                    "constraint_change",
                    true_value=true_limit,
                    true_freshness_time=str(constraint["event_time"]),
                )
            )

    return (
        resources,
        crew,
        availability,
        weather,
        constraints,
        pd.DataFrame(labels, columns=_LABEL_COLUMNS),
    )


def main(seed: int, size: int, out: Path) -> Path:
    """Generate synthetic source CSVs and ``labels.parquet`` under ``out``.

    The raw files contain injected missing/stale/duplicate/conflicting/constraint
    records; the labels file preserves record-level ground truth for evaluation.

    Returns the normalized output directory.
    """
    validate_seed(seed)
    validate_count(size, "size", minimum=1)
    output = Path(out)
    raw = output / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    resources = generate_resources(size, seed)
    crew = generate_crew(size, seed + 1)
    availability = generate_availability(resources, crew, horizon_days=7, seed=seed + 2)
    weather = generate_weather(horizon_days=90, seed=seed + 3)
    constraints = generate_constraints(resources, seed + 4)
    resources, crew, availability, weather, constraints, labels = _inject_synthetic_labels(
        resources,
        crew,
        availability,
        weather,
        constraints,
        seed,
    )

    resources.to_csv(raw / "resources.csv", index=False)
    crew.to_csv(raw / "crew.csv", index=False)
    availability.to_csv(raw / "availability.csv", index=False)
    weather.to_csv(raw / "weather.csv", index=False)
    pd.DataFrame(constraints).to_csv(raw / "constraints.csv", index=False)
    try:
        labels.to_parquet(output / "labels.parquet", index=False)
    except ImportError as error:
        raise RuntimeError(
            "Writing labels.parquet requires a parquet engine; "
            "install the project pyarrow dependency"
        ) from error
    return output


def cli() -> None:
    """Command-line entry point for seeded synthetic dataset generation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--size", type=int, default=100)
    parser.add_argument("--out", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    main(args.seed, args.size, args.out)


if __name__ == "__main__":
    cli()
