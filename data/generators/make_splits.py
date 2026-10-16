"""Create deterministic chronological train/validation/test ML datasets."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from data.generators._common import validate_seed

_SPLIT_NAMES = ("train", "val", "test")


def _ordered_splits(frame: pd.DataFrame, time_column: str, seed: int) -> dict[str, pd.DataFrame]:
    """Sort rows by event time, seeded-shuffle ties, and divide chronologically."""
    if len(frame) < 3:
        raise ValueError(f"at least three rows are required to split {time_column}")
    if time_column not in frame:
        raise ValueError(f"split data is missing timestamp column {time_column!r}")
    ordered = frame.copy()
    timestamps = pd.to_datetime(ordered[time_column], utc=True, errors="coerce")
    if timestamps.isna().any():
        raise ValueError(f"split data contains invalid {time_column} values")
    rng = np.random.default_rng(seed)
    ordered["__sort_time"] = timestamps
    ordered["__tie_breaker"] = rng.random(len(ordered))
    ordered = ordered.sort_values(["__sort_time", "__tie_breaker"], kind="stable")
    size = len(ordered)
    train_end = min(max(1, int(size * 0.70)), size - 2)
    validation_end = min(max(train_end + 1, train_end + int(size * 0.15)), size - 1)
    partitions = {
        "train": ordered.iloc[:train_end],
        "val": ordered.iloc[train_end:validation_end],
        "test": ordered.iloc[validation_end:],
    }
    clean: dict[str, pd.DataFrame] = {}
    for name, part in partitions.items():
        clean[name] = part.drop(columns=["__sort_time", "__tie_breaker"]).reset_index(drop=True)
    return clean


def _record_pairs(resources: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Create positive same-entity and negative distinct-entity Ditto examples."""
    if len(resources) < 2:
        raise ValueError("at least two resource rows are required to create pair splits")
    needed = {"record_id", "entity_id", "event_time"}
    if not needed <= set(resources.columns):
        raise ValueError("resource data lacks pair-generation fields")
    records = resources.to_dict(orient="records")
    entity_groups: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        entity_groups[str(record["entity_id"])].append(index)

    selected_pairs: dict[tuple[int, int], str] = {}
    for indices in entity_groups.values():
        for left_pos in range(len(indices)):
            for right_pos in range(left_pos + 1, len(indices)):
                selected_pairs[(indices[left_pos], indices[right_pos])] = "match"

    different_entity_pairs = len(records) * (len(records) - 1) // 2 - len(selected_pairs)
    negative_target = min(max(1, len(selected_pairs) * 2, len(records) * 2), different_entity_pairs)
    rng = np.random.default_rng(seed)
    negatives: set[tuple[int, int]] = set()
    attempts = 0
    max_attempts = max(100, negative_target * 30)
    while len(negatives) < negative_target and attempts < max_attempts:
        left_index, right_index = sorted(
            rng.choice(len(records), size=2, replace=False).tolist()
        )
        if records[left_index]["entity_id"] != records[right_index]["entity_id"]:
            negatives.add((left_index, right_index))
        attempts += 1
    if not negatives:
        raise ValueError("resource records do not yield distinct-entity negative pairs")
    selected_pairs.update({pair: "no_match" for pair in negatives})

    rows: list[dict[str, str]] = []
    for (left_index, right_index), label in sorted(selected_pairs.items()):
        left, right = records[left_index], records[right_index]
        event_time = max(str(left["event_time"]), str(right["event_time"]))
        left_payload = {
            key: value
            for key, value in left.items()
            if key not in {"record_id", "source_id"}
        }
        right_payload = {
            key: value
            for key, value in right.items()
            if key not in {"record_id", "source_id"}
        }
        rows.append(
            {
                "pair_id": f"pair:{left['record_id']}:{right['record_id']}",
                "left_record_id": str(left["record_id"]),
                "right_record_id": str(right["record_id"]),
                "left": json.dumps(
                    left_payload, sort_keys=True, separators=(",", ":"), default=str
                ),
                "right": json.dumps(
                    right_payload, sort_keys=True, separators=(",", ":"), default=str
                ),
                "label": label,
                "event_time": event_time,
            }
        )
    pairs = pd.DataFrame(rows)
    if pairs.empty or pairs["label"].nunique() < 2:
        raise ValueError("resource records must yield both positive and negative match pairs")
    return pairs


def main(seed: int, root: Path = Path("data/processed")) -> Path:
    """Write time-ordered pair, temporal-graph, and forecast splits under ``root/splits``.

    Reads the synthetic CSVs and labels parquet produced by ``generate_all.main``.
    The labels parquet is validated and retained in the dataset root; individual
    split files keep source rows chronologically separated.
    """
    validate_seed(seed)
    data_root = Path(root)
    raw_path = data_root / "raw"
    resources = pd.read_csv(raw_path / "resources.csv")
    crew = pd.read_csv(raw_path / "crew.csv")
    availability = pd.read_csv(raw_path / "availability.csv")
    weather = pd.read_csv(raw_path / "weather.csv")
    constraints = pd.read_csv(raw_path / "constraints.csv")
    labels_path = data_root / "labels.parquet"
    if not labels_path.is_file():
        raise FileNotFoundError(labels_path)
    labels = pd.read_parquet(labels_path)
    expected_labels = {
        "record_id",
        "fault_type",
        "true_value",
        "duplicate_of",
        "conflict_group_id",
        "true_freshness_time",
    }
    if not expected_labels <= set(labels.columns):
        raise ValueError("labels parquet does not match the documented ground-truth schema")
    if len(resources) < 6:
        raise ValueError(
            "at least six resource rows are required to create clean non-empty forecast splits"
        )

    typed_frames = []
    for source_type, frame in (
        ("resource", resources),
        ("crew", crew),
        ("availability", availability),
        ("weather", weather),
        ("constraint", constraints),
    ):
        typed = frame.copy()
        typed["source_type"] = source_type
        typed_frames.append(typed)
    graph_records = pd.concat(typed_frames, ignore_index=True, sort=False)
    graph_records = graph_records.merge(labels, on="record_id", how="left")
    pairs = _record_pairs(resources, seed)
    faulted_resource_ids = set(
        labels.loc[labels["record_id"].isin(resources["record_id"]), "record_id"]
    )
    clean_resources = resources.loc[~resources["record_id"].isin(faulted_resource_ids)]
    forecast = clean_resources[
        ["record_id", "entity_id", "event_time", "capacity_mw", "region"]
    ].copy()

    split_sets = {
        "pairs": _ordered_splits(pairs, "event_time", seed),
        "graph": _ordered_splits(graph_records, "event_time", seed + 1),
        "forecast": _ordered_splits(forecast, "event_time", seed + 2),
    }
    split_dir = data_root / "splits"
    split_dir.mkdir(parents=True, exist_ok=True)
    for dataset_name, partitions in split_sets.items():
        for split_name in _SPLIT_NAMES:
            frame = partitions[split_name]
            if dataset_name == "graph":
                frame.to_parquet(split_dir / f"{dataset_name}_{split_name}.parquet", index=False)
            else:
                frame.to_csv(split_dir / f"{dataset_name}_{split_name}.csv", index=False)
    return split_dir


def cli() -> None:
    """Generate splits with an optional explicit seed and dataset root."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--root", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    main(args.seed, args.root)


if __name__ == "__main__":
    cli()
