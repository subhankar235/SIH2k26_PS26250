"""Ditto pair serialization, forward shape, training, and inference tests."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import torch
from torch import nn

import ml.entity_matching.ditto_model as ditto_module
import ml.entity_matching.infer as infer_module
import ml.entity_matching.train as train_module
from ml.entity_matching.ditto_model import DittoMatcher, serialize_pair


class _FakeEncoder(nn.Module):
    """Small local encoder that exposes the Hugging Face model surface used by Ditto."""

    def __init__(self) -> None:
        super().__init__()
        self.config = SimpleNamespace(hidden_size=4, hidden_dropout_prob=0.0)
        self.embedding = nn.Embedding(512, 4)

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor):
        del attention_mask
        return SimpleNamespace(last_hidden_state=self.embedding(input_ids), pooler_output=None)

    def save_pretrained(self, path: str | Path) -> None:
        Path(path).mkdir(parents=True, exist_ok=True)


class _FakeTokenizer:
    """Stable tokenizer stub for CPU-only training/inference tests."""

    def __call__(
        self,
        texts: str | list[str],
        *,
        padding: str | bool = "max_length",
        truncation: bool = True,
        max_length: int = 32,
        return_tensors: str = "pt",
    ) -> dict[str, torch.Tensor]:
        del padding, truncation, return_tensors
        batch = [texts] if isinstance(texts, str) else texts
        ids = torch.zeros((len(batch), max_length), dtype=torch.long)
        mask = torch.zeros_like(ids)
        for row, text in enumerate(batch):
            tokens = [ord(char) % 511 + 1 for char in text[:max_length]]
            if tokens:
                ids[row, : len(tokens)] = torch.tensor(tokens)
                mask[row, : len(tokens)] = 1
        return {"input_ids": ids, "attention_mask": mask}

    def save_pretrained(self, path: str | Path) -> None:
        directory = Path(path)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "tokenizer.stub").write_text("fake", encoding="utf-8")


def _fake_mlflow(monkeypatch) -> list[tuple[str, object]]:
    """Install an in-memory MLflow module and return captured API calls."""
    from contextlib import nullcontext

    calls: list[tuple[str, object]] = []
    fake = ModuleType("mlflow")
    fake.set_experiment = lambda name: (  # type: ignore[attr-defined]
        calls.append(("experiment", name)) or SimpleNamespace(experiment_id="test-experiment")
    )
    fake.start_run = lambda **kwargs: (  # type: ignore[attr-defined]
        calls.append(("start", kwargs))
        or nullcontext(SimpleNamespace(info=SimpleNamespace(run_id="r1")))
    )
    fake.log_params = lambda value: calls.append(("params", value))  # type: ignore[attr-defined]
    fake.set_tags = lambda value: calls.append(("tags", value))  # type: ignore[attr-defined]
    fake.log_metrics = lambda value, step=None: calls.append(  # type: ignore[attr-defined]
        ("metrics", (value, step))
    )
    fake.log_artifacts = lambda value: calls.append(("artifacts", value))  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mlflow", fake)
    return calls


def test_serialize_pair_is_sorted_deterministic_and_handles_structured_values() -> None:
    """Produce the documented Ditto markers in stable key order without mutating input."""
    left = {"name": "Alpha  Station", "capacity": 3, "metadata": {"b": 2, "a": 1}}
    right = {"name": "Alpha Station", "capacity": 4}
    original = dict(left)

    serialized = serialize_pair(left, right)

    assert serialized == (
        '[COL] capacity [VAL] 3 [COL] metadata [VAL] {"a":1,"b":2} '
        '[COL] name [VAL] Alpha Station [SEP] '
        '[COL] capacity [VAL] 4 [COL] name [VAL] Alpha Station'
    )
    assert left == original
    assert serialize_pair({"b": 2, "a": 1}, {}) == serialize_pair({"a": 1, "b": 2}, {})
    with pytest.raises(TypeError):
        serialize_pair([], {})  # type: ignore[arg-type]


def test_ditto_matcher_returns_match_no_match_logits(monkeypatch) -> None:
    """Initialize against a stub encoder and verify [batch, match/no_match] logits."""
    monkeypatch.setattr(
        ditto_module.AutoModel,
        "from_pretrained",
        lambda _base: _FakeEncoder(),
    )
    model = DittoMatcher("tiny-test-encoder")
    logits = model(torch.ones((3, 7), dtype=torch.long), torch.ones((3, 7), dtype=torch.long))

    assert logits.shape == (3, 2)
    with pytest.raises(ValueError, match="shapes must match"):
        model(torch.ones((1, 3), dtype=torch.long), torch.ones((1, 2), dtype=torch.long))


def test_ditto_training_artifact_loads_and_scores_pairs(monkeypatch, tmp_path: Path) -> None:
    """Train one deterministic CPU epoch, save artifacts, reload, and return a probability."""
    calls = _fake_mlflow(monkeypatch)
    fake_tokenizer = _FakeTokenizer()
    monkeypatch.setattr(
        train_module.AutoTokenizer,
        "from_pretrained",
        lambda _base: fake_tokenizer,
    )
    monkeypatch.setattr(
        ditto_module.AutoModel,
        "from_pretrained",
        lambda _base: _FakeEncoder(),
    )
    monkeypatch.setattr(
        infer_module.AutoTokenizer,
        "from_pretrained",
        lambda _base, **_kwargs: fake_tokenizer,
    )
    pairs_path = tmp_path / "pairs.csv"
    rows = [
        ({"name": "same", "capacity": 2}, {"capacity": 2, "name": "same"}, "match"),
        ({"name": "different"}, {"name": "different"}, "no_match"),
        ({"asset": "north"}, {"asset": "north"}, "match"),
        ({"asset": "one"}, {"asset": "two"}, "no_match"),
    ]
    with pairs_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["left", "right", "label"])
        writer.writeheader()
        for left, right, label in rows:
            writer.writerow(
                {"left": json.dumps(left), "right": json.dumps(right), "label": label}
            )

    config = train_module.DittoConfig(
        data_path=pairs_path,
        output_dir=tmp_path / "model",
        base="tiny-test-encoder",
        epochs=1,
        batch_size=2,
        max_length=24,
        validation_fraction=0.5,
    )
    output = train_module.train(config, seed=37)
    assert (output / "classifier.pt").is_file()
    assert (output / "encoder").is_dir()
    assert (output / "tokenizer").is_dir()
    assert any(call[0] == "metrics" for call in calls)
    assert any(call[0] == "artifacts" for call in calls)

    model = infer_module.load(output)
    assert isinstance(model, DittoMatcher)
    probability = infer_module.predict_proba(
        model,
        {"name": "same", "capacity": 2},
        {"name": "same", "capacity": 2},
    )
    assert 0 <= probability <= 1
