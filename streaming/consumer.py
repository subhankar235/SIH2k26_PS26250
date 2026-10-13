"""Consumer-side event validation helpers."""

from typing import Any


def is_valid_telemetry(event: dict[str, Any]) -> bool:
    """Check the minimal envelope expected for telemetry events."""
    return bool(event.get("asset_id")) and isinstance(event.get("observed_at"), str)
