"""Deterministic fault-injection scenarios for simulation runs."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Fault:
    asset_id: str
    starts_at_hour: int
    duration_hours: int


def validate_fault(fault: Fault) -> None:
    """Reject malformed fault intervals."""
    if not fault.asset_id:
        raise ValueError("asset_id must not be empty")
    if fault.starts_at_hour < 0 or fault.duration_hours <= 0:
        raise ValueError("fault interval must start at/after zero and have positive duration")
