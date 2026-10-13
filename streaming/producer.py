"""Small transport-independent telemetry producer interface."""

from collections.abc import Mapping
from typing import Any, Protocol


class EventSink(Protocol):
    """Interface implemented by a Kafka-backed event sink."""

    def publish(self, topic: str, key: str, payload: Mapping[str, Any]) -> None: ...


def telemetry_topic(region: str) -> str:
    """Build the canonical telemetry topic name for a region."""
    return f"grid.telemetry.{region.lower().replace(' ', '-')}.v1"
