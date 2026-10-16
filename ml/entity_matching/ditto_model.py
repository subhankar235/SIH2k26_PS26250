"""Ditto-style transformer classifier and deterministic pair serialization."""

from __future__ import annotations

import json
from typing import Any

from torch import Tensor, nn
from transformers import AutoModel


def _field_value(value: Any) -> str:
    """Render one scalar or structured record value without mapping-order variance."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _serialize_record(record: dict[str, Any]) -> str:
    """Render one record as sorted Ditto [COL]/[VAL] segments."""
    if not isinstance(record, dict):
        raise TypeError("record pair members must be dictionaries")
    fields: list[str] = []
    keys = sorted((str(key) for key in record), key=lambda key: (key.casefold(), key))
    values_by_string = {str(key): value for key, value in record.items()}
    if len(values_by_string) != len(record):
        raise ValueError("record keys must have unique string representations")
    for key in keys:
        fields.extend(
            ("[COL]", " ".join(key.split()), "[VAL]", _field_value(values_by_string[key]))
        )
    return " ".join(fields)


def serialize_pair(a: dict[str, Any], b: dict[str, Any]) -> str:
    """Serialize two records into deterministic Ditto text with a pair separator."""
    return f"{_serialize_record(a)} [SEP] {_serialize_record(b)}"


class DittoMatcher(nn.Module):
    """Transformer encoder with a binary classification head ordered [match, no_match]."""

    def __init__(self, base: str = "distilbert-base-uncased") -> None:
        """Load a pretrained Hugging Face encoder and initialize a two-class head."""
        super().__init__()
        if not isinstance(base, str) or not base.strip():
            raise ValueError("base must be a non-empty Hugging Face model name or path")
        self.base = base
        self.encoder = AutoModel.from_pretrained(base)
        self.tokenizer: Any | None = None
        hidden_size = getattr(self.encoder.config, "hidden_size", None)
        if hidden_size is None:
            hidden_size = getattr(self.encoder.config, "dim", None)
        if not isinstance(hidden_size, int) or hidden_size < 1:
            raise ValueError("pretrained encoder config does not expose a valid hidden size")
        dropout = float(getattr(self.encoder.config, "hidden_dropout_prob", 0.1))
        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(hidden_size, 2)

    def forward(self, input_ids: Tensor, attention_mask: Tensor) -> Tensor:
        """Return logits shaped ``[batch, 2]`` in ``[match, no_match]`` class order."""
        if input_ids.ndim != 2 or attention_mask.ndim != 2:
            raise ValueError("input_ids and attention_mask must have shape [batch, sequence]")
        if input_ids.shape != attention_mask.shape:
            raise ValueError("input_ids and attention_mask shapes must match")
        output = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        pooled = getattr(output, "pooler_output", None)
        if pooled is None:
            last_hidden_state = getattr(output, "last_hidden_state", None)
            if last_hidden_state is None:
                raise ValueError("pretrained encoder output lacks last_hidden_state")
            pooled = last_hidden_state[:, 0]
        return self.classifier(self.dropout(pooled))  # type: ignore[no-any-return]
