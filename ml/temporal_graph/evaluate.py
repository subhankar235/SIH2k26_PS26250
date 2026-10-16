"""Compare trained graph models with rule and frequency-statistical baselines."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from ml.temporal_graph.dataset import TemporalData, build_temporal_graph
from ml.temporal_graph.strgnn.model import StrGNNModel
from ml.temporal_graph.tgn.model import TGNModel
from ml.temporal_graph.tgn.train import _align_vocab, _chunks


def _load_artifact(path: Path) -> tuple[dict[str, Any], dict[str, torch.Tensor]]:
    """Load and validate a saved graph-model state and its vocabulary metadata."""
    metadata_path = path / "metadata.json"
    weights_path = path / "model.pt"
    if not metadata_path.is_file() or not weights_path.is_file():
        raise FileNotFoundError(
            f"Missing trained model artifact in {path}; train the model before evaluation"
        )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError(f"Model metadata must be a JSON object: {metadata_path}")
    state = torch.load(weights_path, map_location="cpu", weights_only=True)
    if not isinstance(state, dict) or not all(isinstance(key, str) for key in state):
        raise ValueError(f"Invalid model state dictionary: {weights_path}")
    return metadata, state


def _f1(labels: np.ndarray, predicted: np.ndarray) -> float:
    """Calculate positive-class F1 with zero-safe precision and recall."""
    truth = labels.astype(bool)
    guess = predicted.astype(bool)
    tp = int(np.count_nonzero(truth & guess))
    fp = int(np.count_nonzero(~truth & guess))
    fn = int(np.count_nonzero(truth & ~guess))
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    return 2 * precision * recall / max(1e-12, precision + recall)


def _auroc(labels: np.ndarray, scores: np.ndarray) -> float:
    """Compute ROC AUC by the Mann–Whitney rank statistic, averaging ties."""
    truth = labels.astype(bool)
    positives = int(truth.sum())
    negatives = len(truth) - positives
    if not positives or not negatives:
        return float("nan")
    order = np.argsort(scores, kind="stable")
    sorted_scores = scores[order]
    sorted_truth = truth[order]
    rank_sum = 0.0
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and sorted_scores[end] == sorted_scores[start]:
            end += 1
        average_rank = ((start + 1) + end) / 2.0
        rank_sum += average_rank * int(sorted_truth[start:end].sum())
        start = end
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def _metrics(
    labels: np.ndarray, predicted: np.ndarray, scores: np.ndarray
) -> dict[str, float]:
    """Return event-level precision, recall, F1, and AUROC."""
    truth = labels.astype(bool)
    guess = predicted.astype(bool)
    tp = int(np.count_nonzero(truth & guess))
    fp = int(np.count_nonzero(~truth & guess))
    fn = int(np.count_nonzero(truth & ~guess))
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    return {
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / max(1e-12, precision + recall),
        "auroc": _auroc(labels, scores),
    }


def paired_bootstrap_f1_ci(
    labels: np.ndarray,
    candidate: np.ndarray,
    baseline: np.ndarray,
    *,
    n_resamples: int = 1_000,
    seed: int = 42,
) -> tuple[float, float]:
    """Bootstrap the paired per-event F1 difference (candidate minus baseline)."""
    labels = np.asarray(labels, dtype=np.int8)
    candidate = np.asarray(candidate, dtype=np.int8)
    baseline = np.asarray(baseline, dtype=np.int8)
    if labels.ndim != 1 or candidate.shape != labels.shape or baseline.shape != labels.shape:
        raise ValueError("labels and paired predictions must be one-dimensional and equal length")
    if not len(labels) or n_resamples < 100:
        raise ValueError("bootstrap requires data and at least 100 resamples")
    rng = np.random.default_rng(seed)
    differences = np.empty(n_resamples, dtype=np.float64)
    size = len(labels)
    for sample_index in range(n_resamples):
        indexes = rng.integers(0, size, size=size)
        differences[sample_index] = _f1(labels[indexes], candidate[indexes]) - _f1(
            labels[indexes], baseline[indexes]
        )
    low, high = np.quantile(differences, [0.025, 0.975])
    return float(low), float(high)


def _model_data(data: TemporalData, metadata: dict[str, Any]) -> TemporalData:
    """Map a split's categories into the exact vocabularies stored with a model."""
    vocab_data = TemporalData(
        source_ids=torch.empty(0, dtype=torch.long),
        entity_ids=torch.empty(0, dtype=torch.long),
        attribute_ids=torch.empty(0, dtype=torch.long),
        value_hashes=torch.empty(0, dtype=torch.long),
        timestamps=torch.empty(0, dtype=torch.long),
        time_deltas=torch.empty(0, dtype=torch.float32),
        labels=torch.empty(0, dtype=torch.long),
        link_labels=torch.empty(0, dtype=torch.float32),
        record_ids=(),
        source_vocabulary=tuple(metadata["source_vocabulary"]),
        entity_vocabulary=tuple(metadata["entity_vocabulary"]),
        attribute_vocabulary=tuple(metadata["attribute_vocabulary"]),
    )
    return _align_vocab(data, vocab_data)


def _tgn_scores(data: TemporalData, artifact: Path) -> np.ndarray:
    """Load a real TGN artifact and score fault events chronologically."""
    metadata, state = _load_artifact(artifact)
    aligned = _model_data(data, metadata)
    model = TGNModel(
        len(metadata["source_vocabulary"]),
        len(metadata["entity_vocabulary"]),
        len(metadata["attribute_vocabulary"]),
        hidden_dim=int(metadata["hidden_dim"]),
    )
    model.load_state_dict(state, strict=True)
    model.eval()
    result: list[torch.Tensor] = []
    model.reset_memory()
    with torch.inference_mode():
        for chunk in _chunks(aligned, 128):
            result.append(torch.softmax(model(chunk).node_logits, dim=-1)[:, 1].cpu())
    return torch.cat(result).numpy()


def _strgnn_scores(data: TemporalData, artifact: Path) -> np.ndarray:
    """Load a real structural snapshot artifact and score its graph edges."""
    metadata, state = _load_artifact(artifact)
    aligned = _model_data(data, metadata)
    model = StrGNNModel(
        len(metadata["source_vocabulary"]),
        len(metadata["entity_vocabulary"]),
        len(metadata["attribute_vocabulary"]),
        hidden_dim=int(metadata["hidden_dim"]),
    )
    model.load_state_dict(state, strict=True)
    model.eval()
    with torch.inference_mode():
        return torch.softmax(model(aligned), dim=-1)[:, 1].cpu().numpy()


def _baseline_scores(train: TemporalData, test: TemporalData) -> tuple[np.ndarray, np.ndarray]:
    """Fit a deterministic unseen-value rule and train-frequency anomaly score."""
    test = _align_vocab(test, train)
    train_keys = list(
        zip(
            train.source_ids.tolist(),
            train.attribute_ids.tolist(),
            train.value_hashes.tolist(),
            strict=True,
        )
    )
    test_keys = list(
        zip(
            test.source_ids.tolist(),
            test.attribute_ids.tolist(),
            test.value_hashes.tolist(),
            strict=True,
        )
    )
    counts = Counter(train_keys)
    clean_deltas = train.time_deltas[train.labels == 0].numpy()
    gap_threshold = float(np.quantile(clean_deltas, 0.995)) if len(clean_deltas) else 0.0
    rule_scores = np.asarray(
        [float(counts.get(key, 0) == 0 or float(delta) > gap_threshold)
         for key, delta in zip(test_keys, test.time_deltas.tolist(), strict=True)],
        dtype=np.float64,
    )
    frequencies = np.asarray([counts.get(key, 0) for key in test_keys], dtype=np.float64)
    statistical_scores = -np.log((frequencies + 1.0) / (len(train_keys) + len(counts)))
    if len(clean_deltas):
        scale = max(float(np.std(clean_deltas)), 1e-6)
        statistical_scores += np.maximum(0.0, test.time_deltas.numpy() - gap_threshold) / scale
    clean_train_scores = np.asarray(
        [
            -np.log((counts[key] + 1.0) / (len(train_keys) + len(counts)))
            for key, label in zip(train_keys, train.labels.tolist(), strict=True)
            if label == 0
        ],
        dtype=np.float64,
    )
    threshold = (
        float(np.quantile(clean_train_scores, 0.99))
        if len(clean_train_scores)
        else float("inf")
    )
    return rule_scores, statistical_scores - threshold


def evaluate_all(split: str = "test") -> pd.DataFrame:
    """Evaluate trained TGN/StrGNN against rule and statistical baselines.

    Model artifacts are loaded from ``ml/artifacts/{tgn,strgnn}`` by default; set
    ``AIRPOWER_TGN_ARTIFACT`` or ``AIRPOWER_STRGNN_ARTIFACT`` to override them.
    Learned models are marked adopted only when their paired-bootstrap 95% F1
    improvement over the rule baseline has a strictly positive lower confidence
    bound. Missing model artifacts raise an error rather than fabricating outputs.
    """
    if split not in {"train", "val", "test"}:
        raise ValueError("split must be 'train', 'val', or 'test'")
    data_root = Path(os.getenv("AIRPOWER_TEMPORAL_DATA", "data/processed/sih_product/splits"))
    train_data = build_temporal_graph(data_root, "train")
    test_data = build_temporal_graph(data_root, split)
    y_true = test_data.labels.numpy()
    rule_scores, statistical_scores = _baseline_scores(train_data, test_data)
    rule_pred = rule_scores >= 0.5
    rule_metrics = _metrics(y_true, rule_pred, rule_scores)
    rows: list[dict[str, Any]] = [
        {
            "model": "rule_based",
            **rule_metrics,
            "f1_delta_vs_rule": 0.0,
            "ci_low": 0.0,
            "ci_high": 0.0,
            "adopted": False,
        }
    ]
    statistical_pred = statistical_scores > 0
    statistical_metrics = _metrics(y_true, statistical_pred, statistical_scores)
    statistical_low, statistical_high = paired_bootstrap_f1_ci(
        y_true, statistical_pred, rule_pred, seed=42
    )
    rows.append(
        {
            "model": "statistical_frequency",
            **statistical_metrics,
            "f1_delta_vs_rule": statistical_metrics["f1"] - rule_metrics["f1"],
            "ci_low": statistical_low,
            "ci_high": statistical_high,
            "adopted": False,
        }
    )

    candidates = (
        (
            "TGN",
            Path(os.getenv("AIRPOWER_TGN_ARTIFACT", "ml/artifacts/tgn")),
            _tgn_scores,
        ),
        (
            "StrGNN",
            Path(os.getenv("AIRPOWER_STRGNN_ARTIFACT", "ml/artifacts/strgnn")),
            _strgnn_scores,
        ),
    )
    for name, artifact, score_model in candidates:
        scores = score_model(test_data, artifact)
        predicted = scores >= 0.5
        metrics = _metrics(y_true, predicted, scores)
        low, high = paired_bootstrap_f1_ci(y_true, predicted, rule_pred, seed=42)
        rows.append(
            {
                "model": name,
                **metrics,
                "f1_delta_vs_rule": metrics["f1"] - rule_metrics["f1"],
                "ci_low": low,
                "ci_high": high,
                "adopted": bool(low > 0.0),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "model", "precision", "recall", "f1", "auroc", "f1_delta_vs_rule",
            "ci_low", "ci_high", "adopted",
        ],
    )
