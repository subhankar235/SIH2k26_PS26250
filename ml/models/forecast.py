"""Baseline demand forecast contract."""

from collections.abc import Sequence


def moving_average(values: Sequence[float], window: int = 3) -> float:
    """Return a simple trailing mean baseline for non-empty observations."""
    if window < 1:
        raise ValueError("window must be at least 1")
    if not values:
        raise ValueError("values must not be empty")
    sample = values[-window:]
    return sum(sample) / len(sample)
