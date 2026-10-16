"""Tests for chronological temporal graph encoding and TGN training artifacts."""

from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sqlalchemy import create_engine, text

import ml.temporal_graph.strgnn.train as strgnn_train_module
import ml.temporal_graph.tgn.train as train_module
from ml.temporal_graph.dataset import build_temporal_graph
from ml.temporal_graph.evaluate import evaluate_all, paired_bootstrap_f1_ci
from ml.temporal_graph.strgnn.model import StrGNNModel
from ml.temporal_graph.tgn.model import model_for_data


def _write_graph_split(root: Path, split: str, rows: list[dict[str, object]]) -> None:
    """Write one local graph parquet split for dataset and trainer tests."""
    pd.DataFrame(rows).to_parquet(root / f"graph_{split}.parquet", index=False)


def _rows(prefix: str, offset: int = 0) -> list[dict[str, object]]:
    """Create small but mixed-label temporal events with known timestamps."""
    return [
        {
            "record_id": f"{prefix}-{i}",
            "entity_id": f"entity-{i % 2}",
            "source_id": f"source-{i % 2}",
            "source_type": "resource",
            "event_time": f"2026-01-01T00:00:{offset + i:02d}+00:00",
            "capacity_mw": 100.0 + i,
            "fault_type": "stale" if i % 2 else None,
        }
        for i in range(6)
    ]


def test_build_temporal_graph_keeps_chronology_and_feature_encodings(tmp_path: Path) -> None:
    """Encode source/entity/attribute/value/time features and fault labels in time order."""
    _write_graph_split(tmp_path, "train", list(reversed(_rows("train"))))

    graph = build_temporal_graph(tmp_path, "train")

    assert len(graph) == 6
    assert graph.record_ids == tuple(f"train-{i}" for i in range(6))
    assert graph.source_ids.dtype == torch.long
    assert graph.entity_ids.dtype == torch.long
    assert graph.attribute_ids.dtype == torch.long
    assert graph.value_hashes.dtype == torch.long
    assert graph.timestamps.tolist() == sorted(graph.timestamps.tolist())
    assert graph.time_deltas.shape == (6,)
    assert graph.labels.tolist() == [0, 1, 0, 1, 0, 1]
    assert graph.link_labels.tolist() == [0.0, 0.0, 1.0, 1.0, 1.0, 1.0]
    assert graph.num_sources == 2
    assert graph.num_entities == 2


def test_build_temporal_graph_accepts_database_url_and_splits_by_time(tmp_path: Path) -> None:
    """Read normalized rows from SQL and form chronological, non-overlapping splits."""
    database = tmp_path / "temporal.db"
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE source (id TEXT PRIMARY KEY, source_type TEXT)"))
        connection.execute(
            text(
                "CREATE TABLE record (id TEXT PRIMARY KEY, entity_id TEXT, source_id TEXT, "
                "normalised_payload TEXT, event_time TEXT, flags TEXT)"
            )
        )
        connection.execute(
            text("INSERT INTO source (id, source_type) VALUES ('source-a', 'resource')")
        )
        for i in range(10):
            connection.execute(
                text(
                    "INSERT INTO record VALUES (:id,:entity,:source,:payload,:time,:flags)"
                ),
                {
                    "id": f"db-{i}",
                    "entity": f"entity-{i % 3}",
                    "source": "source-a",
                    "payload": '{"capacity_mw": 100}',
                    "time": f"2026-01-01T00:00:{i:02d}+00:00",
                    "flags": '["stale"]' if i == 3 else "[]",
                },
            )
    engine.dispose()

    train = build_temporal_graph(f"sqlite:///{database}", "train")
    validation = build_temporal_graph(f"sqlite:///{database}", "val")
    test = build_temporal_graph(f"sqlite:///{database}", "test")

    assert len(train) + len(validation) + len(test) == 10
    assert train.timestamps.max() < validation.timestamps.min()
    assert validation.timestamps.max() < test.timestamps.min()
    assert sum(int(graph.labels.sum()) for graph in (train, validation, test)) == 1


def test_tgn_forward_and_real_training_write_reloadable_weights(
    tmp_path: Path, monkeypatch
) -> None:
    """Train actual torch weights on parquet events and verify model artifact contents."""
    for split in ("train", "val", "test"):
        _write_graph_split(tmp_path, split, _rows(split, offset=10 if split != "train" else 0))
    monkeypatch.setattr(train_module, "start_run", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(train_module, "log_metrics", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(train_module, "log_artifact_path", lambda *_args, **_kwargs: None)
    data = build_temporal_graph(tmp_path, "train")
    model = model_for_data(data, hidden_dim=8, dropout=0.0)
    output = model(data, reset_memory=True)
    assert output.node_logits.shape == (6, 2)
    assert output.link_logits.shape == (6,)

    artifact = train_module.train(
        train_module.TGNConfig(
            data_root=tmp_path,
            output_dir=tmp_path / "artifact",
            epochs=1,
            hidden_dim=8,
            chunk_size=2,
        ),
        seed=19,
    )

    metadata = json.loads((artifact / "metadata.json").read_text(encoding="utf-8"))
    assert (artifact / "model.pt").is_file()
    assert metadata["training_events"] == 6
    assert metadata["feature_schema"] == [
        "source_id", "entity_id", "attribute", "value_hash", "time_delta"
    ]


def test_strgnn_snapshot_forward_and_training_artifact(tmp_path: Path, monkeypatch) -> None:
    """Train and persist structural snapshot weights on actual labeled parquet events."""
    for split in ("train", "val", "test"):
        _write_graph_split(tmp_path, split, _rows(split, offset=10 if split != "train" else 0))
    monkeypatch.setattr(strgnn_train_module, "start_run", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(strgnn_train_module, "log_metrics", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(strgnn_train_module, "log_artifact_path", lambda *_args, **_kwargs: None)
    data = build_temporal_graph(tmp_path, "train")
    model = StrGNNModel(data.num_sources, data.num_entities, data.num_attributes, hidden_dim=8)
    logits = model(data)
    assert logits.shape == (6, 2)
    torch.nn.functional.cross_entropy(logits, data.labels).backward()
    assert model.edge_classifier[-1].weight.grad is not None

    artifact = strgnn_train_module.train(
        strgnn_train_module.StrGNNConfig(
            data_root=tmp_path,
            output_dir=tmp_path / "strgnn-artifact",
            epochs=1,
            hidden_dim=8,
        ),
        seed=31,
    )
    metadata = json.loads((artifact / "metadata.json").read_text(encoding="utf-8"))
    assert (artifact / "model.pt").is_file()
    assert metadata["snapshot_frequency"] == "UTC day"


def test_evaluation_loads_real_models_and_applies_bootstrap_gate(
    tmp_path: Path, monkeypatch
) -> None:
    """Evaluate saved learned weights beside real baselines with paired confidence bounds."""
    for split in ("train", "val", "test"):
        _write_graph_split(tmp_path, split, _rows(split, offset=10 if split != "train" else 0))
    for module in (train_module, strgnn_train_module):
        monkeypatch.setattr(module, "start_run", lambda *_args, **_kwargs: nullcontext())
        monkeypatch.setattr(module, "log_metrics", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(module, "log_artifact_path", lambda *_args, **_kwargs: None)
    tgn_artifact = train_module.train(
        train_module.TGNConfig(
            data_root=tmp_path, output_dir=tmp_path / "tgn-eval", epochs=1,
            hidden_dim=8, chunk_size=3,
        ),
        seed=41,
    )
    strgnn_artifact = strgnn_train_module.train(
        strgnn_train_module.StrGNNConfig(
            data_root=tmp_path, output_dir=tmp_path / "strgnn-eval", epochs=1, hidden_dim=8
        ),
        seed=41,
    )
    monkeypatch.setenv("AIRPOWER_TEMPORAL_DATA", str(tmp_path))
    monkeypatch.setenv("AIRPOWER_TGN_ARTIFACT", str(tgn_artifact))
    monkeypatch.setenv("AIRPOWER_STRGNN_ARTIFACT", str(strgnn_artifact))

    results = evaluate_all()

    assert results["model"].tolist() == ["rule_based", "statistical_frequency", "TGN", "StrGNN"]
    assert results.loc[results["model"].isin(["TGN", "StrGNN"]), "adopted"].isin(
        [True, False]
    ).all()
    low, high = paired_bootstrap_f1_ci(
        np.asarray([1, 1, 0, 0]),
        np.asarray([1, 1, 1, 0]),
        np.asarray([1, 0, 0, 0]),
        n_resamples=200,
        seed=17,
    )
    assert low <= high
