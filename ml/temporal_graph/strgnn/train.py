"""Train, evaluate, and persist a seeded structural-snapshot GNN."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.nn import functional as F

from ml.common.mlflow_utils import log_artifact_path, log_metrics, start_run
from ml.common.seed import set_all_seeds
from ml.temporal_graph.dataset import TemporalData, build_temporal_graph
from ml.temporal_graph.strgnn.model import StrGNNModel
from ml.temporal_graph.tgn.train import _align_vocab


@dataclass(frozen=True)
class StrGNNConfig:
    """Dataset, artifact, and optimization settings for structural snapshots."""

    data_root: Path = Path("data/processed/sih_product/splits")
    output_dir: Path = Path("ml/artifacts/strgnn")
    epochs: int = 1
    learning_rate: float = 1e-3
    batch_size: int = 1
    hidden_dim: int = 32
    max_train_events: int | None = None
    experiment: str = "temporal-graph-strgnn"

    def __post_init__(self) -> None:
        if self.epochs < 1 or self.hidden_dim < 4 or self.batch_size < 1:
            raise ValueError("epochs/batch_size must be positive and hidden_dim must be at least 4")
        if not np.isfinite(self.learning_rate) or self.learning_rate <= 0:
            raise ValueError("learning_rate must be finite and positive")
        if self.max_train_events is not None and self.max_train_events < 1:
            raise ValueError("max_train_events must be positive when specified")
        if not self.experiment.strip():
            raise ValueError("experiment must not be empty")


def _take(data: TemporalData, start: int, end: int) -> TemporalData:
    """Select a chronological contiguous event window."""
    return replace(
        data,
        source_ids=data.source_ids[start:end],
        entity_ids=data.entity_ids[start:end],
        attribute_ids=data.attribute_ids[start:end],
        value_hashes=data.value_hashes[start:end],
        timestamps=data.timestamps[start:end],
        time_deltas=data.time_deltas[start:end],
        labels=data.labels[start:end],
        link_labels=data.link_labels[start:end],
        record_ids=data.record_ids[start:end],
    )


def _snapshot_ranges(data: TemporalData) -> list[tuple[int, int]]:
    """Return contiguous event ranges for UTC-day graph snapshots."""
    days = torch.div(data.timestamps, 86_400, rounding_mode="floor")
    _, counts = torch.unique_consecutive(days, return_counts=True)
    ranges: list[tuple[int, int]] = []
    offset = 0
    for count in counts.tolist():
        ranges.append((offset, offset + count))
        offset += count
    return ranges


def _f1(model: StrGNNModel, data: TemporalData) -> float:
    """Evaluate fault F1 over the chronological snapshot sequence."""
    model.eval()
    with torch.inference_mode():
        predicted = model(data).argmax(dim=-1).cpu() == 1
    truth = data.labels.bool()
    tp = int((predicted & truth).sum())
    fp = int((predicted & ~truth).sum())
    fn = int((~predicted & truth).sum())
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    return 2 * precision * recall / max(1e-12, precision + recall)


def _fit(cfg: StrGNNConfig, seed: int) -> tuple[StrGNNModel, dict[str, Any]]:
    """Train chronological daily snapshots using supervised event fault labels."""
    train_data = build_temporal_graph(cfg.data_root, "train")
    if cfg.max_train_events is not None and len(train_data) > cfg.max_train_events:
        train_data = _take(train_data, 0, cfg.max_train_events)
    validation = _align_vocab(build_temporal_graph(cfg.data_root, "val"), train_data)
    test = _align_vocab(build_temporal_graph(cfg.data_root, "test"), train_data)
    model = StrGNNModel(
        train_data.num_sources,
        train_data.num_entities,
        train_data.num_attributes,
        hidden_dim=cfg.hidden_dim,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.learning_rate)
    counts = torch.bincount(train_data.labels, minlength=2).to(torch.float32)
    weights = counts.sum() / (2 * counts.clamp_min(1))
    losses: list[float] = []
    for _epoch in range(cfg.epochs):
        model.train()
        epoch_losses: list[float] = []
        snapshots = [
            _take(train_data, start, end) for start, end in _snapshot_ranges(train_data)
        ]
        for batch_start in range(0, len(snapshots), cfg.batch_size):
            batch = snapshots[batch_start : batch_start + cfg.batch_size]
            optimizer.zero_grad(set_to_none=True)
            batch_losses = []
            for snapshot in batch:
                logits = model(snapshot)
                batch_losses.append(F.cross_entropy(logits, snapshot.labels, weight=weights))
            loss = torch.stack(batch_losses).mean()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            epoch_losses.append(float(loss.detach().cpu()))
        losses.append(float(np.mean(epoch_losses)))
    model.eval()
    validation_f1 = _f1(model, validation)
    test_f1 = _f1(model, test)
    metadata: dict[str, Any] = {
        "seed": seed,
        "model": "StrGNNModel",
        "snapshot_frequency": "UTC day",
        "feature_schema": ["source_id", "entity_id", "attribute", "value_hash", "time_delta"],
        "source_vocabulary": train_data.source_vocabulary,
        "entity_vocabulary": train_data.entity_vocabulary,
        "attribute_vocabulary": train_data.attribute_vocabulary,
        "hidden_dim": cfg.hidden_dim,
        "epochs": cfg.epochs,
        "training_events": len(train_data),
        "training_label_counts": {"clean": int(counts[0]), "fault": int(counts[1])},
        "epoch_losses": losses,
        "validation_f1": validation_f1,
        "test_f1": test_f1,
    }
    return model, metadata


def train(cfg: StrGNNConfig | dict[str, Any], seed: int) -> Path:
    """Fit a structural snapshot GNN and save its state and vocabulary metadata."""
    if isinstance(cfg, dict):
        cfg = StrGNNConfig(**cfg)
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    set_all_seeds(seed)
    model, metadata = _fit(cfg, seed)
    output_dir = Path(cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    params = {**asdict(cfg), "seed": seed}
    with start_run(cfg.experiment, params, tags={"model": "strgnn", "seed": str(seed)}):
        log_metrics(
            {
                "validation_f1": metadata["validation_f1"],
                "test_f1": metadata["test_f1"],
                "final_training_loss": metadata["epoch_losses"][-1],
            }
        )
        torch.save(model.state_dict(), output_dir / "model.pt")
        (output_dir / "metadata.json").write_text(
            json.dumps(metadata, sort_keys=True, indent=2), encoding="utf-8"
        )
        log_artifact_path(output_dir)
    return output_dir


def main() -> None:
    """Load YAML hyperparameters and train with explicit config and seed arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    import yaml

    raw = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("StrGNN YAML config must contain a mapping")
    config = dict(raw)
    configured_seed = config.pop("seed", None)
    seed = args.seed if args.seed is not None else configured_seed
    data_path = config.pop("data_path", None)
    if data_path is not None:
        config["data_root"] = data_path
    if "lr" in config:
        config["learning_rate"] = config.pop("lr")
    if seed is None:
        raise ValueError("provide --seed or a seed value in the YAML config")
    train(StrGNNConfig(**config), int(seed))


if __name__ == "__main__":
    main()
