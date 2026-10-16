"""Train and track a seeded Ditto pair classifier from a labelled CSV dataset."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import Tensor
from torch.utils.data import DataLoader, TensorDataset
from transformers import AutoTokenizer

from ml.common.mlflow_utils import log_artifact_path, log_metrics, start_run
from ml.common.seed import set_all_seeds
from ml.entity_matching.ditto_model import DittoMatcher, serialize_pair


@dataclass(frozen=True)
class DittoConfig:
    """Training inputs and bounded optimizer/model settings."""

    data_path: Path
    validation_path: Path | None = None
    test_path: Path | None = None
    output_dir: Path = Path("ml/artifacts/ditto")
    base: str = "distilbert-base-uncased"
    epochs: int = 3
    learning_rate: float = 2e-5
    batch_size: int = 16
    max_length: int = 256
    validation_fraction: float = 0.2
    experiment: str = "entity-matching-ditto"

    def __post_init__(self) -> None:
        if not str(self.data_path):
            raise ValueError("data_path must not be empty")
        if not self.base.strip() or not self.experiment.strip():
            raise ValueError("base and experiment must not be empty")
        if self.epochs < 1 or self.batch_size < 1 or self.max_length < 8:
            raise ValueError("epochs, batch_size, and max_length must be positive")
        if not np.isfinite(self.learning_rate) or self.learning_rate <= 0:
            raise ValueError("learning_rate must be finite and positive")
        if not 0 <= self.validation_fraction < 1:
            raise ValueError("validation_fraction must be in [0, 1)")


def _label(value: object) -> int:
    """Map a labelled pair to Ditto class ids: match=0, no_match=1."""
    if isinstance(value, bool):
        return 0 if value else 1
    normalized = str(value).strip().casefold()
    if normalized in {"match", "matched", "true", "yes", "1"}:
        return 0
    if normalized in {"no_match", "non-match", "non_match", "false", "no", "0"}:
        return 1
    raise ValueError(f"Unsupported entity-match label: {value!r}")


def _record(value: object, row_number: int, field: str) -> dict[str, Any]:
    """Parse a CSV JSON object column into a record mapping."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        raise ValueError(f"row {row_number}: {field} must be a JSON object")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"row {row_number}: {field} is not valid JSON") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"row {row_number}: {field} must decode to an object")
    return parsed


def _load_pairs(path: Path) -> tuple[list[str], list[int]]:
    """Load CSV rows with ``left``/``right`` JSON records and a binary label."""
    if not path.is_file():
        raise FileNotFoundError(path)
    texts: list[str] = []
    labels: list[int] = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"left", "right", "label"}
        if reader.fieldnames is None or not required <= set(reader.fieldnames):
            raise ValueError("pair CSV must contain left, right, and label columns")
        for row_number, row in enumerate(reader, start=2):
            left = _record(row.get("left"), row_number, "left")
            right = _record(row.get("right"), row_number, "right")
            texts.append(serialize_pair(left, right))
            labels.append(_label(row.get("label")))
    if not texts:
        raise ValueError("pair CSV contains no training examples")
    if len(set(labels)) < 2:
        raise ValueError("pair CSV must contain positive and negative examples")
    return texts, labels


def _encode(tokenizer: Any, texts: list[str], max_length: int) -> TensorDataset:
    """Tokenize a materialized text list into tensors for deterministic batching."""
    encoded = tokenizer(
        texts,
        padding="max_length",
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    )
    return TensorDataset(encoded["input_ids"], encoded["attention_mask"])


def _evaluate(
    model: DittoMatcher,
    loader: DataLoader[tuple[Tensor, ...]],
    device: torch.device,
) -> dict[str, float]:
    """Compute binary match precision, recall, and F1 on a deterministic data loader."""
    true_positive = false_positive = false_negative = 0
    model.eval()
    with torch.inference_mode():
        for input_ids, attention_mask, labels in loader:
            logits = model(input_ids.to(device), attention_mask.to(device))
            predicted_match = logits.argmax(dim=1).cpu() == 0
            actual_match = labels == 0
            true_positive += int((predicted_match & actual_match).sum().item())
            false_positive += int((predicted_match & ~actual_match).sum().item())
            false_negative += int((~predicted_match & actual_match).sum().item())
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def train(cfg: DittoConfig, seed: int) -> Path:
    """Train Ditto, log metrics/parameters, and save a loadable inference artifact."""
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    set_all_seeds(seed)
    texts, labels = _load_pairs(Path(cfg.data_path))
    indices = np.random.default_rng(seed).permutation(len(texts)).tolist()
    if cfg.validation_path is not None:
        validation_texts, validation_label_values = _load_pairs(Path(cfg.validation_path))
        validation_labels = torch.tensor(validation_label_values, dtype=torch.long)
        training_indices = indices
    else:
        validation_count = (
            max(1, round(len(indices) * cfg.validation_fraction))
            if cfg.validation_fraction > 0 and len(indices) > 1
            else 0
        )
        validation_indices = indices[:validation_count]
        training_indices = indices[validation_count:] if validation_count else indices
        validation_texts = [texts[index] for index in validation_indices]
        validation_labels = torch.tensor(
            [labels[index] for index in validation_indices], dtype=torch.long
        )
    validation_count = len(validation_texts)
    tokenizer = AutoTokenizer.from_pretrained(cfg.base)  # type: ignore[no-untyped-call]
    train_texts = [texts[index] for index in training_indices]
    train_labels = torch.tensor([labels[index] for index in training_indices], dtype=torch.long)
    train_encoded = tokenizer(
        train_texts,
        padding="max_length",
        truncation=True,
        max_length=cfg.max_length,
        return_tensors="pt",
    )
    train_data = TensorDataset(
        train_encoded["input_ids"], train_encoded["attention_mask"], train_labels
    )
    train_class_counts = torch.bincount(train_labels, minlength=2).to(dtype=torch.float32)
    class_weights = train_class_counts.sum() / (2 * train_class_counts.clamp_min(1))
    batch_rng = torch.Generator().manual_seed(seed)
    train_loader = DataLoader(
        train_data,
        batch_size=cfg.batch_size,
        shuffle=True,
        generator=batch_rng,
    )
    validation_loader: DataLoader[tuple[Tensor, ...]] | None = None
    if validation_count:
        validation_encoded = tokenizer(
            validation_texts,
            padding="max_length",
            truncation=True,
            max_length=cfg.max_length,
            return_tensors="pt",
        )
        validation_data = TensorDataset(
            validation_encoded["input_ids"],
            validation_encoded["attention_mask"],
            validation_labels,
        )
        validation_loader = DataLoader(
            validation_data,
            batch_size=cfg.batch_size,
            shuffle=False,
        )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = DittoMatcher(cfg.base).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.learning_rate)
    output_dir = Path(cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, Any] = {
        "seed": seed,
        "base": cfg.base,
        "max_length": cfg.max_length,
        "class_order": ["match", "no_match"],
        "training_examples": len(training_indices),
        "validation_examples": validation_count,
        "training_label_counts": {
            "match": int(train_class_counts[0].item()),
            "no_match": int(train_class_counts[1].item()),
        },
        "test_examples": 0,
    }

    params = {**asdict(cfg), "seed": seed}
    with start_run(cfg.experiment, params, tags={"model": "ditto", "seed": str(seed)}) as _run:
        for epoch in range(cfg.epochs):
            model.train()
            loss_sum = 0.0
            batches = 0
            for input_ids, attention_mask, batch_labels in train_loader:
                optimizer.zero_grad(set_to_none=True)
                logits = model(input_ids.to(device), attention_mask.to(device))
                loss = torch.nn.functional.cross_entropy(
                    logits,
                    batch_labels.to(device),
                    weight=class_weights.to(device),
                )
                loss.backward()  # type: ignore[no-untyped-call]
                optimizer.step()
                loss_sum += float(loss.detach().cpu().item())
                batches += 1

            if validation_loader is not None:
                metrics = _evaluate(model, validation_loader, device)
            else:
                metrics = _evaluate(model, train_loader, device)
            metrics["loss"] = loss_sum / max(1, batches)
            log_metrics(metrics, step=epoch)

        test_metrics: dict[str, float] = {}
        if cfg.test_path is not None:
            test_texts, test_label_values = _load_pairs(Path(cfg.test_path))
            test_encoded = tokenizer(
                test_texts,
                padding="max_length",
                truncation=True,
                max_length=cfg.max_length,
                return_tensors="pt",
            )
            test_data = TensorDataset(
                test_encoded["input_ids"],
                test_encoded["attention_mask"],
                torch.tensor(test_label_values, dtype=torch.long),
            )
            test_metrics = _evaluate(
                model,
                DataLoader(test_data, batch_size=cfg.batch_size, shuffle=False),
                device,
            )
            metadata["test_examples"] = len(test_texts)
            metadata["test_metrics"] = test_metrics
            log_metrics(
                {f"test_{name}": value for name, value in test_metrics.items()},
                step=cfg.epochs,
            )

        encoder_path = output_dir / "encoder"
        tokenizer_path = output_dir / "tokenizer"
        model.encoder.save_pretrained(encoder_path)
        tokenizer.save_pretrained(tokenizer_path)
        torch.save(model.classifier.state_dict(), output_dir / "classifier.pt")
        metadata_path = output_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(metadata, sort_keys=True, indent=2), encoding="utf-8"
        )
        log_artifact_path(output_dir)
    return output_dir


def main() -> None:
    """Read YAML config and train from the documented ``--config --seed`` CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as error:
        raise RuntimeError("CLI YAML loading requires PyYAML") from error
    raw = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Ditto YAML config must contain a mapping")
    config_seed = args.seed if args.seed is not None else raw.get("seed")
    if config_seed is None:
        raise ValueError("provide --seed or a seed value in the YAML config")
    if not isinstance(raw.get("data_path"), str) or not raw["data_path"].strip():
        raise ValueError("Ditto config requires a non-empty data_path")
    learning_rate = raw.get("learning_rate", raw.get("lr", 2e-5))
    if isinstance(learning_rate, bool) or not isinstance(learning_rate, (int, float)):
        raise ValueError("learning_rate must be numeric")
    config = DittoConfig(
        data_path=Path(raw["data_path"]),
        validation_path=Path(str(raw["validation_path"]))
        if raw.get("validation_path")
        else None,
        test_path=Path(str(raw["test_path"])) if raw.get("test_path") else None,
        output_dir=Path(raw.get("output_dir", "ml/artifacts/ditto")),
        base=str(raw.get("base", "distilbert-base-uncased")),
        epochs=int(raw.get("epochs", 3)),
        learning_rate=float(learning_rate),
        batch_size=int(raw.get("batch_size", 16)),
        max_length=int(raw.get("max_length", 256)),
        validation_fraction=float(raw.get("validation_fraction", 0.2)),
        experiment=str(raw.get("experiment", "entity-matching-ditto")),
    )
    train(config, int(config_seed))


if __name__ == "__main__":
    main()
