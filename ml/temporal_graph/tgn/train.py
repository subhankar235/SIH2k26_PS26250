"""Train, evaluate, and persist a seeded temporal graph network."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import Tensor
from torch.nn import functional as F

from ml.common.mlflow_utils import log_artifact_path, log_metrics, start_run
from ml.common.seed import set_all_seeds
from ml.temporal_graph.dataset import TemporalData, build_temporal_graph
from ml.temporal_graph.tgn.model import TGNModel, model_for_data


@dataclass(frozen=True)
class TGNConfig:
    """Input locations and bounded training parameters for the temporal graph model."""

    data_root: Path = Path("data/processed/sih_product/splits")
    output_dir: Path = Path("ml/artifacts/tgn")
    epochs: int = 1
    learning_rate: float = 1e-3
    hidden_dim: int = 32
    chunk_size: int = 128
    max_train_events: int | None = None
    experiment: str = "temporal-graph-tgn"

    def __post_init__(self) -> None:
        if self.epochs < 1 or self.hidden_dim < 4 or self.chunk_size < 1:
            raise ValueError("epochs/chunk_size must be positive and hidden_dim >= 4")
        if not np.isfinite(self.learning_rate) or self.learning_rate <= 0:
            raise ValueError("learning_rate must be finite and positive")
        if self.max_train_events is not None and self.max_train_events < 1:
            raise ValueError("max_train_events must be positive when specified")
        if not str(self.experiment).strip():
            raise ValueError("experiment must not be empty")


def _align_vocab(data: TemporalData, train_data: TemporalData) -> TemporalData:
    """Encode validation/test categories using train vocabularies; unseen values map to 0."""
    source_map = {name: index for index, name in enumerate(train_data.source_vocabulary)}
    entity_map = {name: index for index, name in enumerate(train_data.entity_vocabulary)}
    attr_map = {name: index for index, name in enumerate(train_data.attribute_vocabulary)}
    source_map.setdefault("<unknown>", 0)
    entity_map.setdefault("<unknown>", 0)
    attr_map.setdefault("<unknown>", 0)
    source_ids = torch.tensor(
        [source_map.get(data.source_vocabulary[int(index)], 0) for index in data.source_ids],
        dtype=torch.long,
    )
    entity_ids = torch.tensor(
        [entity_map.get(data.entity_vocabulary[int(index)], 0) for index in data.entity_ids],
        dtype=torch.long,
    )
    attribute_ids = torch.tensor(
        [attr_map.get(data.attribute_vocabulary[int(index)], 0) for index in data.attribute_ids],
        dtype=torch.long,
    )
    return replace(
        data,
        source_ids=source_ids,
        entity_ids=entity_ids,
        attribute_ids=attribute_ids,
        source_vocabulary=train_data.source_vocabulary,
        entity_vocabulary=train_data.entity_vocabulary,
        attribute_vocabulary=train_data.attribute_vocabulary,
    )


def _chunks(data: TemporalData, size: int):
    """Yield chronological windows without shuffling event order."""
    for start in range(0, len(data), size):
        end = min(start + size, len(data))
        yield replace(
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


def _evaluate(model: TGNModel, data: TemporalData, chunk_size: int) -> dict[str, float]:
    """Compute fault-event precision, recall, F1, and AUROC in chronological order."""
    model.eval()
    probabilities: list[Tensor] = []
    labels: list[Tensor] = []
    model.reset_memory()
    with torch.inference_mode():
        for chunk in _chunks(data, chunk_size):
            output = model(chunk, detach_memory=True)
            probabilities.append(torch.softmax(output.node_logits, dim=-1)[:, 1].cpu())
            labels.append(chunk.labels.cpu())
    scores = torch.cat(probabilities)
    truth = torch.cat(labels).to(dtype=torch.bool)
    predicted = scores >= 0.5
    true_positive = int((predicted & truth).sum())
    false_positive = int((predicted & ~truth).sum())
    false_negative = int((~predicted & truth).sum())
    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, true_positive + false_negative)
    f1 = 2 * precision * recall / max(1e-12, precision + recall)
    if truth.any() and (~truth).any():
        ranks = torch.argsort(torch.argsort(scores)).to(torch.float64)
        positives = int(truth.sum())
        negatives = len(truth) - positives
        auc = float(
            (ranks[truth].sum() - positives * (positives - 1) / 2)
            / (positives * negatives)
        )
    else:
        auc = float("nan")
    return {"precision": precision, "recall": recall, "f1": f1, "auroc": auc}


def _run_training(cfg: TGNConfig, seed: int) -> tuple[TGNModel, dict[str, Any]]:
    """Fit the model chronologically, using truncated BPTT between event chunks."""
    train_data = build_temporal_graph(cfg.data_root, "train")
    if cfg.max_train_events is not None and len(train_data) > cfg.max_train_events:
        train_data = replace(
            train_data,
            source_ids=train_data.source_ids[: cfg.max_train_events],
            entity_ids=train_data.entity_ids[: cfg.max_train_events],
            attribute_ids=train_data.attribute_ids[: cfg.max_train_events],
            value_hashes=train_data.value_hashes[: cfg.max_train_events],
            timestamps=train_data.timestamps[: cfg.max_train_events],
            time_deltas=train_data.time_deltas[: cfg.max_train_events],
            labels=train_data.labels[: cfg.max_train_events],
            link_labels=train_data.link_labels[: cfg.max_train_events],
            record_ids=train_data.record_ids[: cfg.max_train_events],
        )
    validation = _align_vocab(build_temporal_graph(cfg.data_root, "val"), train_data)
    test = _align_vocab(build_temporal_graph(cfg.data_root, "test"), train_data)
    model = model_for_data(train_data, hidden_dim=cfg.hidden_dim)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.learning_rate)
    counts = torch.bincount(train_data.labels, minlength=2).to(torch.float32)
    class_weights = counts.sum() / (2 * counts.clamp_min(1))
    epoch_losses: list[float] = []
    for _epoch in range(cfg.epochs):
        model.train()
        model.reset_memory()
        losses: list[float] = []
        for chunk in _chunks(train_data, cfg.chunk_size):
            optimizer.zero_grad(set_to_none=True)
            output = model(chunk, detach_memory=True)
            node_loss = F.cross_entropy(
                output.node_logits,
                chunk.labels,
                weight=class_weights,
            )
            link_loss = F.binary_cross_entropy_with_logits(
                output.link_logits,
                chunk.link_labels,
                pos_weight=torch.tensor(
                    max(
                        1.0,
                        float((chunk.link_labels == 0).sum())
                        / max(1, int((chunk.link_labels == 1).sum())),
                    ),
                    dtype=output.link_logits.dtype,
                ),
            )
            loss = node_loss + link_loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        epoch_losses.append(float(np.mean(losses)))
    validation_metrics = _evaluate(model, validation, cfg.chunk_size)
    test_metrics = _evaluate(model, test, cfg.chunk_size)
    metadata: dict[str, Any] = {
        "seed": seed,
        "model": "TGNModel",
        "feature_schema": ["source_id", "entity_id", "attribute", "value_hash", "time_delta"],
        "source_vocabulary": train_data.source_vocabulary,
        "entity_vocabulary": train_data.entity_vocabulary,
        "attribute_vocabulary": train_data.attribute_vocabulary,
        "hidden_dim": cfg.hidden_dim,
        "epochs": cfg.epochs,
        "training_events": len(train_data),
        "training_label_counts": {"clean": int(counts[0]), "fault": int(counts[1])},
        "training_repeated_link_events": int(train_data.link_labels.sum()),
        "epoch_losses": epoch_losses,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
    }
    return model, metadata


def train(cfg: TGNConfig | dict[str, Any], seed: int) -> Path:
    """Train a temporal graph network, log experiment metrics, and save its artifact."""
    if isinstance(cfg, dict):
        cfg = TGNConfig(**cfg)
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    set_all_seeds(seed)
    model, metadata = _run_training(cfg, seed)
    output_dir = Path(cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = output_dir / "metadata.json"
    state_path = output_dir / "model.pt"
    params = {**asdict(cfg), "seed": seed}
    with start_run(cfg.experiment, params, tags={"model": "tgn", "seed": str(seed)}):
        log_metrics(
            {
                f"validation_{name}": value
                for name, value in metadata["validation_metrics"].items()
                if np.isfinite(value)
            }
        )
        log_metrics(
            {
                f"test_{name}": value
                for name, value in metadata["test_metrics"].items()
                if np.isfinite(value)
            }
        )
        torch.save(model.state_dict(), state_path)
        metadata_path.write_text(
            json.dumps(metadata, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8"
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
        raise ValueError("TGN YAML config must contain a mapping")
    config = dict(raw)
    configured_seed = config.pop("seed", None)
    seed = args.seed if args.seed is not None else configured_seed
    data_path = config.pop("data_path", None)
    if data_path is not None:
        config["data_root"] = data_path
    if "lr" in config:
        config["learning_rate"] = config.pop("lr")
    if "batch_size" in config:
        config["chunk_size"] = config.pop("batch_size")
    if seed is None:
        raise ValueError("provide --seed or a seed value in the YAML config")
    train(TGNConfig(**config), int(seed))


if __name__ == "__main__":
    main()
