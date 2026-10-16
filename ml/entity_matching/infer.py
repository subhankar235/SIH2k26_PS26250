"""Load a trained Ditto artifact and score record pairs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch
from transformers import AutoTokenizer

from ml.entity_matching.ditto_model import DittoMatcher, serialize_pair


def load(path: Path) -> DittoMatcher:
    """Load a local Ditto artifact directory produced by ``train``.

    The directory contains ``encoder/``, ``tokenizer/``, ``classifier.pt``, and
    ``metadata.json``. No network access is needed when the artifact is complete.
    """
    artifact = Path(path)
    metadata_path = artifact / "metadata.json"
    classifier_path = artifact / "classifier.pt"
    encoder_path = artifact / "encoder"
    tokenizer_path = artifact / "tokenizer"
    for required in (metadata_path, classifier_path, encoder_path, tokenizer_path):
        if not required.exists():
            raise FileNotFoundError(f"Ditto artifact is incomplete: {required}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("Ditto artifact metadata must be a JSON object")
    if metadata.get("class_order") != ["match", "no_match"]:
        raise ValueError("Ditto artifact has an unsupported output class order")
    max_length = metadata.get("max_length", 256)
    if not isinstance(max_length, int) or isinstance(max_length, bool) or max_length < 8:
        raise ValueError("Ditto artifact max_length must be an integer of at least 8")
    model = DittoMatcher(str(encoder_path))
    classifier_state = torch.load(classifier_path, map_location="cpu", weights_only=True)
    model.classifier.load_state_dict(classifier_state)
    tokenizer = AutoTokenizer.from_pretrained(  # type: ignore[no-untyped-call]
        str(tokenizer_path), local_files_only=True
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.tokenizer = tokenizer
    model.max_length = max_length
    return model.to(device).eval()


def predict_proba(model: DittoMatcher, a: dict[str, Any], b: dict[str, Any]) -> float:
    """Return the probability of a match (class index 0) for one record pair."""
    if not isinstance(model, DittoMatcher) or model.tokenizer is None:
        raise TypeError("model must be loaded with ml.entity_matching.infer.load")
    text = serialize_pair(a, b)
    encoded = model.tokenizer(
        text,
        truncation=True,
        max_length=getattr(model, "max_length", 256),
        return_tensors="pt",
    )
    model_device = next(model.parameters()).device
    input_ids = encoded["input_ids"].to(model_device)
    attention_mask = encoded["attention_mask"].to(model_device)
    with torch.inference_mode():
        probability = torch.softmax(model(input_ids, attention_mask), dim=-1)[0, 0]
    return float(probability.detach().cpu().item())
