"""Reproducibility, schema, labels, and chronological split tests for synthetic data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from data.generators.generate_all import main as generate_all
from data.generators.generate_availability import generate as generate_availability
from data.generators.generate_constraints import generate as generate_constraints
from data.generators.generate_crew import generate as generate_crew
from data.generators.generate_resources import generate as generate_resources
from data.generators.generate_weather import generate as generate_weather
from data.generators.make_splits import main as make_splits


def test_each_source_generator_is_seeded_and_matches_its_columns() -> None:
    """Return reproducible resource, crew, availability, weather, and constraint data."""
    resources = generate_resources(8, 101)
    crew = generate_crew(6, 102)
    availability = generate_availability(resources, crew, 3, 103)
    weather = generate_weather(3, 104)
    constraints = generate_constraints(resources, 105)

    assert resources.equals(generate_resources(8, 101))
    assert crew.equals(generate_crew(6, 102))
    assert availability.equals(generate_availability(resources, crew, 3, 103))
    assert weather.equals(generate_weather(3, 104))
    assert constraints == generate_constraints(resources, 105)
    assert len(resources) == 8
    assert len(crew) == 6
    assert len(availability) == 24
    assert len(weather) == 12
    assert len(constraints) == 8
    assert resources["entity_id"].str.startswith("resource-").all()

    with pytest.raises(ValueError, match="non-negative"):
        generate_resources(2, -1)
    with pytest.raises(ValueError, match="horizon_days"):
        generate_weather(0, 1)


def test_generate_all_writes_raw_sources_and_ground_truth_labels(
    monkeypatch, tmp_path: Path
) -> None:
    """Generate all documented fault classes and write the documented Parquet schema."""
    parquet_frames: dict[str, pd.DataFrame] = {}

    def fake_to_parquet(frame: pd.DataFrame, path, index: bool = False, **_kwargs) -> None:
        del index
        location = Path(path)
        location.parent.mkdir(parents=True, exist_ok=True)
        frame.to_pickle(location)
        parquet_frames[str(location)] = frame.copy()

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fake_to_parquet)

    output = generate_all(seed=7, size=8, out=tmp_path / "generated")
    raw = output / "raw"
    assert output == tmp_path / "generated"
    assert {
        "resources.csv",
        "crew.csv",
        "availability.csv",
        "weather.csv",
        "constraints.csv",
    } == {path.name for path in raw.glob("*.csv")}
    labels = pd.read_pickle(output / "labels.parquet")
    assert list(labels.columns) == [
        "record_id",
        "fault_type",
        "true_value",
        "duplicate_of",
        "conflict_group_id",
        "true_freshness_time",
    ]
    assert set(labels["fault_type"]) >= {
        "missing",
        "stale",
        "duplicate",
        "conflicting",
        "constraint_change",
    }
    assert labels["record_id"].notna().all()

    other = generate_all(seed=7, size=8, out=tmp_path / "repeat")
    filenames = ("resources.csv", "crew.csv", "availability.csv", "weather.csv", "constraints.csv")
    for filename in filenames:
        assert (raw / filename).read_bytes() == (other / "raw" / filename).read_bytes()
    other_labels = pd.read_pickle(other / "labels.parquet")
    pd.testing.assert_frame_equal(labels, other_labels)


def test_make_splits_writes_nonempty_chronological_ml_partitions(
    monkeypatch, tmp_path: Path
) -> None:
    """Create repeatable train/val/test pair, graph, and forecast splits."""
    def fake_to_parquet(frame: pd.DataFrame, path, index: bool = False, **_kwargs) -> None:
        del index
        frame.to_pickle(path)

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fake_to_parquet)
    monkeypatch.setattr(pd, "read_parquet", lambda path, **_kwargs: pd.read_pickle(path))
    root = generate_all(seed=23, size=10, out=tmp_path / "processed")

    split_dir = make_splits(seed=29, root=root)
    assert split_dir == root / "splits"
    for dataset, extension in (("pairs", "csv"), ("graph", "parquet"), ("forecast", "csv")):
        partitions = {
            name: (
                pd.read_csv(split_dir / f"{dataset}_{name}.{extension}")
                if extension == "csv"
                else pd.read_pickle(split_dir / f"{dataset}_{name}.{extension}")
            )
            for name in ("train", "val", "test")
        }
        assert all(not frame.empty for frame in partitions.values())
        for earlier, later in (("train", "val"), ("val", "test")):
            earlier_end = pd.to_datetime(partitions[earlier]["event_time"], utc=True).max()
            later_start = pd.to_datetime(partitions[later]["event_time"], utc=True).min()
            assert earlier_end <= later_start
        if dataset == "pairs":
            assert {"left", "right", "label"} <= set(partitions["train"].columns)
            assert set(partitions["train"]["label"]) == {"match", "no_match"}

    repeated = make_splits(seed=29, root=root)
    for name in ("pairs_train.csv", "pairs_val.csv", "pairs_test.csv"):
        assert (split_dir / name).read_bytes() == (repeated / name).read_bytes()
