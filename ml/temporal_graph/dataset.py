"""Build chronological temporal-graph event tensors from generated parquet splits."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd
import torch
from sqlalchemy import create_engine, text
from torch import Tensor

_SPLITS = {"train", "val", "test"}
_IDENTIFIER_FIELDS = {
    "record_id", "entity_id", "resource_id", "crew_id", "source_id",
    "event_time", "ingest_time", "fault_type", "true_value", "duplicate_of",
    "conflict_group_id", "true_freshness_time", "flags",
}
_ATTRIBUTE_PRIORITY = (
    "resource_type", "constraint_type", "skills", "available", "temperature_c",
    "capacity_mw", "limit_mw", "wind_speed_mps", "precipitation_mm", "region",
    "available_hours", "active", "name",
)


@dataclass(frozen=True)
class TemporalData:
    """Chronologically sorted record events and encoded temporal-graph features."""

    source_ids: Tensor
    entity_ids: Tensor
    attribute_ids: Tensor
    value_hashes: Tensor
    timestamps: Tensor
    time_deltas: Tensor
    labels: Tensor
    link_labels: Tensor
    record_ids: tuple[str, ...]
    source_vocabulary: tuple[str, ...]
    entity_vocabulary: tuple[str, ...]
    attribute_vocabulary: tuple[str, ...]

    def __len__(self) -> int:
        return int(self.labels.shape[0])

    @property
    def num_sources(self) -> int:
        return len(self.source_vocabulary)

    @property
    def num_entities(self) -> int:
        return len(self.entity_vocabulary)

    @property
    def num_attributes(self) -> int:
        return len(self.attribute_vocabulary)


def _split_frame(source: str | Path, split: str) -> pd.DataFrame:
    """Load one precomputed graph split from a split directory or dataset root."""
    if "://" in str(source):
        return _database_split(str(source), split)
    path = Path(source)
    if path.is_file():
        if path.suffix.lower() != ".parquet":
            raise ValueError("temporal graph split must be a parquet file")
        split_path = path
    else:
        candidates = (
            path / f"graph_{split}.parquet",
            path / "splits" / f"graph_{split}.parquet",
        )
        split_path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if split_path is None:
            raise FileNotFoundError(
                f"No graph_{split}.parquet found in {path} or {path / 'splits'}"
            )
    frame = pd.read_parquet(split_path)
    required = {"record_id", "entity_id", "event_time"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"graph split is missing required columns: {sorted(missing)}")
    return frame


def _database_split(db_url: str, split: str) -> pd.DataFrame:
    """Read normalized records from SQL and apply chronological 70/15/15 splits."""
    engine = create_engine(db_url)
    try:
        with engine.connect() as connection:
            frame = pd.read_sql_query(
                text(
                    "SELECT r.id AS record_id, r.entity_id, r.source_id, "
                    "s.source_type, r.normalised_payload, r.event_time, r.flags "
                    "FROM record AS r JOIN source AS s ON s.id = r.source_id "
                    "ORDER BY r.event_time, r.id"
                ),
                connection,
            )
    finally:
        engine.dispose()
    if frame.empty:
        raise ValueError("database contains no normalized records")

    events: list[dict[str, object]] = []
    for row in frame.to_dict(orient="records"):
        metadata = {
            key: row[key]
            for key in ("record_id", "entity_id", "source_id", "source_type", "event_time")
        }
        payload = row.pop("normalised_payload")
        if isinstance(payload, str):
            payload = json.loads(payload)
        if isinstance(payload, dict):
            row.update(payload)
        row.update(metadata)
        flags = row.pop("flags", None)
        if isinstance(flags, str):
            flags = json.loads(flags)
        row["fault_type"] = ",".join(str(flag) for flag in flags) if flags else None
        events.append(row)
    ordered = pd.DataFrame(events)
    ordered["__timestamp"] = pd.to_datetime(ordered["event_time"], utc=True, errors="coerce")
    if ordered["__timestamp"].isna().any():
        raise ValueError("database contains records with invalid event_time values")
    ordered = ordered.sort_values(["__timestamp", "record_id"], kind="stable").reset_index(
        drop=True
    )
    if len(ordered) < 3:
        raise ValueError("at least three database records are required for time-based splits")
    train_end = min(max(1, int(len(ordered) * 0.70)), len(ordered) - 2)
    validation_end = min(
        max(train_end + 1, train_end + int(len(ordered) * 0.15)), len(ordered) - 1
    )
    bounds = {
        "train": (0, train_end),
        "val": (train_end, validation_end),
        "test": (validation_end, len(ordered)),
    }
    start, end = bounds[split]
    result = ordered.iloc[start:end].drop(columns=["__timestamp"]).reset_index(drop=True)
    return result


def _stable_hash(value: str) -> int:
    """Create a deterministic non-negative 63-bit feature hash."""
    return int.from_bytes(hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest(), "big") & (
        (1 << 63) - 1
    )


def _is_missing(value: object) -> bool:
    """Check scalar missing values without treating structured values as scalars."""
    if value is None:
        return True
    try:
        result = pd.isna(value)
        return bool(result) if not hasattr(result, "__len__") else False
    except (TypeError, ValueError):
        return False


def _event_attribute(row: dict[str, object]) -> str:
    """Select the first available source-specific field represented by this event."""
    for field in _ATTRIBUTE_PRIORITY:
        if field in row and not _is_missing(row[field]):
            return field
    candidates = sorted(
        key for key, value in row.items()
        if key not in _IDENTIFIER_FIELDS and not key.startswith("__") and not _is_missing(value)
    )
    return candidates[0] if candidates else "unknown"


def build_temporal_graph(
    db_url: str | Path,
    split: Literal["train", "val", "test"],
) -> TemporalData:
    """Build event tensors from the requested chronological graph parquet split.

    ``db_url`` accepts either the split directory (containing ``graph_*.parquet``),
    the generated dataset root (containing ``splits/graph_*.parquet``), or the
    parquet path itself. Rows retain the generator's train/validation/test temporal
    boundaries; no records are re-shuffled or allowed to cross split boundaries.
    """
    if split not in _SPLITS:
        raise ValueError("split must be one of 'train', 'val', or 'test'")
    frame = _split_frame(db_url, split)
    if frame.empty:
        raise ValueError(f"graph {split} split contains no events")
    timestamps = pd.to_datetime(frame["event_time"], utc=True, errors="coerce")
    if timestamps.isna().any():
        raise ValueError("graph split contains invalid event_time values")
    frame = frame.assign(__timestamp=timestamps).sort_values(
        ["__timestamp", "record_id"], kind="stable"
    ).reset_index(drop=True)

    rows = frame.to_dict(orient="records")
    sources = tuple(sorted({
        str(row.get("source_id")) if not _is_missing(row.get("source_id"))
        else str(row.get("source_type", "unknown"))
        for row in rows
    }))
    entities = tuple(sorted({str(row["entity_id"]) for row in rows}))
    attributes = tuple(sorted({_event_attribute(row) for row in rows}))
    source_index = {value: index for index, value in enumerate(sources)}
    entity_index = {value: index for index, value in enumerate(entities)}
    attribute_index = {value: index for index, value in enumerate(attributes)}

    timestamp_ns = frame["__timestamp"].astype("datetime64[ns, UTC]").astype("int64")
    seconds = timestamp_ns.to_numpy(dtype="int64") // 1_000_000_000
    deltas = [0.0]
    deltas.extend(
        float(max(0, int(right) - int(left)))
        for left, right in zip(seconds[:-1], seconds[1:], strict=True)
    )
    # Log scaling keeps large real-time gaps numerically stable for the TGN.
    scaled_deltas = [math.log1p(delta) for delta in deltas]

    source_values: list[int] = []
    entity_values: list[int] = []
    attribute_values: list[int] = []
    hashes: list[int] = []
    labels: list[int] = []
    link_labels: list[int] = []
    record_ids: list[str] = []
    seen_links: set[tuple[str, str]] = set()
    for row in rows:
        source = (
            str(row.get("source_id")) if not _is_missing(row.get("source_id"))
            else str(row.get("source_type", "unknown"))
        )
        attribute = _event_attribute(row)
        payload = {
            key: value for key, value in row.items()
            if key not in _IDENTIFIER_FIELDS and key not in {"source_type", "__timestamp"}
            and not _is_missing(value)
        }
        source_values.append(source_index[source])
        entity_values.append(entity_index[str(row["entity_id"])])
        attribute_values.append(attribute_index[attribute])
        hashes.append(_stable_hash(f"{attribute}:{payload.get(attribute, '')}"))
        labels.append(int(not _is_missing(row.get("fault_type"))))
        link = (source, str(row["entity_id"]))
        link_labels.append(int(link in seen_links))
        seen_links.add(link)
        record_ids.append(str(row["record_id"]))

    return TemporalData(
        source_ids=torch.tensor(source_values, dtype=torch.long),
        entity_ids=torch.tensor(entity_values, dtype=torch.long),
        attribute_ids=torch.tensor(attribute_values, dtype=torch.long),
        value_hashes=torch.tensor(hashes, dtype=torch.long),
        timestamps=torch.tensor(seconds, dtype=torch.long),
        time_deltas=torch.tensor(scaled_deltas, dtype=torch.float32),
        labels=torch.tensor(labels, dtype=torch.long),
        link_labels=torch.tensor(link_labels, dtype=torch.float32),
        record_ids=tuple(record_ids),
        source_vocabulary=sources,
        entity_vocabulary=entities,
        attribute_vocabulary=attributes,
    )
