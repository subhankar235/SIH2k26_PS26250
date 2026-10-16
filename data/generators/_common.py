"""Shared validation and deterministic timestamp helpers for source generators."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def validate_seed(seed: int) -> None:
    """Require an integer seed without mutating global RNG state."""
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("seed must be a non-negative integer")


def validate_count(value: int, field: str, *, minimum: int = 0) -> None:
    """Validate a generator row/day count."""
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")


def timestamp_at(hour: int) -> str:
    """Return a deterministic ISO timestamp anchored to a synthetic UTC epoch."""
    return (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=hour)).isoformat()
