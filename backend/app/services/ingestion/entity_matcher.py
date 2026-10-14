"""Resolve ambiguous entity candidates with optional Ditto inference."""

from __future__ import annotations

import importlib
import os
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from backend.app.db.models.record import Record
from backend.app.services.ingestion.normaliser import NormalisedRecord


class MatchResult(BaseModel):
    """Summarize a candidate entity match and review threshold."""

    model_config = ConfigDict(frozen=True)

    is_match: bool
    probability: float = Field(ge=0, le=1)
    flagged: bool


def _tokens(value: Any) -> set[str]:
    """Return case-folded alphanumeric tokens from a value."""
    return set(re.findall(r"[a-z0-9]+", str(value).casefold()))


def _rule_probability(a: NormalisedRecord, b: Record) -> float:
    """Compute deterministic fallback similarity from identity and common fields."""
    if a.entity_id == b.entity_id:
        return 0.98
    entity_similarity = SequenceMatcher(None, a.entity_id, b.entity_id).ratio()
    left = a.normalised_payload
    right = b.normalised_payload
    common = set(left) & set(right)
    if common:
        exact_ratio = sum(left[key] == right[key] for key in common) / len(common)
    else:
        exact_ratio = 0.0
    names_left = _tokens(left.get("name", ""))
    names_right = _tokens(right.get("name", ""))
    name_similarity = (
        float(len(names_left & names_right)) / len(names_left | names_right)
        if names_left and names_right
        else 0.0
    )
    probability: float = (
        0.55 * entity_similarity + 0.25 * float(exact_ratio) + 0.2 * name_similarity
    )
    return min(1.0, probability)


def _ditto_probability(a: NormalisedRecord, b: Record) -> float | None:
    """Call an installed Ditto inference module when model configuration exists."""
    model_path = Path(os.getenv("DITTO_MODEL_PATH", "ml/artifacts/ditto/model"))
    try:
        inference = importlib.import_module("ml.entity_matching.infer")
        model = inference.load(model_path)
        probability = inference.predict_proba(
            model,
            a.normalised_payload,
            b.normalised_payload,
        )
    except (ImportError, FileNotFoundError, AttributeError):
        return None
    probability_value = cast(float, probability)
    return max(0.0, min(1.0, probability_value))


def match(
    a: NormalisedRecord,
    b: Record,
    threshold: float = 0.9,
    low: float = 0.5,
) -> MatchResult:
    """Evaluate an ambiguous candidate and flag uncertain matches.

    Args:
        a: Incoming normalized record.
        b: Persisted candidate record.
        threshold: Probability at or above which the candidate is accepted as a match.
        low: Probability at or above which a non-match is flagged for review.

    Returns:
        Match decision, probability, and manual-review flag.

    Raises:
        ValueError: If thresholds are not ordered within [0, 1].
    """
    if not 0 <= low < threshold <= 1:
        raise ValueError("thresholds must satisfy 0 <= low < threshold <= 1")
    probability = _ditto_probability(a, b)
    if probability is None:
        probability = _rule_probability(a, b)
    return MatchResult(
        is_match=probability >= threshold,
        probability=probability,
        flagged=low <= probability < threshold,
    )
