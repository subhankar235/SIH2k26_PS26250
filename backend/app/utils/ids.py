"""UUID generation and stable canonical JSON fingerprints."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


def new_id() -> UUID:
    """Return a fresh random UUID suitable for persisted identifiers."""
    return uuid4()


def _json_default(value: object) -> object:
    """Convert common typed values to deterministic JSON primitives."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def stable_hash(obj: Any) -> str:
    """Return SHA-256 of canonical JSON, independent of mapping/set order.

    JSON NaN and infinities are rejected instead of producing non-standard hashes.
    """
    canonical = json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_json_default,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
