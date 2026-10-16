"""Reproducible synthetic fault scenarios and a minimal system-under-test protocol."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Scenario:
    """Seed-independent scenario definition supplied to the simulation runner."""

    name: str
    severity: float = 0.5
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GroundTruth:
    """Fault labels retained separately from observations for metric computation."""

    labels: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class RunResult:
    """Deterministic output from ingest, detection, planning, and verification."""

    scenario: str
    seed: int
    events: tuple[dict[str, Any], ...]
    labels: GroundTruth
    detections: tuple[str, ...]
    feasible: bool
    failed: bool
    recovery_time: float


class SystemUnderTest(Protocol):
    """Minimum interface exercised by a stress scenario."""

    def ingest(self, events: list[dict[str, Any]]) -> None: ...

    def detect(self) -> list[str]: ...

    def plan(self) -> Any: ...

    def verify(self, plan: Any) -> bool: ...


class SyntheticSystem:
    """Small deterministic baseline implementation for API-launched simulations."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    def ingest(self, events: list[dict[str, Any]]) -> None:
        self._events = list(events)

    def detect(self) -> list[str]:
        detected: list[str] = []
        for event in self._events:
            if (
                event.get("capacity_mw") is None
                or event.get("observed_at_hour") != event.get("event_hour")
                or "source_values" in event
                or "constraint_change" in event
            ):
                detected.append(str(event["event_id"]))
        return detected

    def plan(self) -> dict[str, Any]:
        feasible = all(
            change.get("new_limit", 0) >= 0
            for event in self._events
            if (change := event.get("constraint_change")) is not None
        )
        return {"feasible": feasible}

    def verify(self, plan: Any) -> bool:
        return bool(isinstance(plan, dict) and plan.get("feasible") is True)


_FAULTS_BY_SCENARIO: dict[str, tuple[str, ...]] = {
    "baseline_clean": (),
    "heavy_staleness": ("stale",),
    "source_conflict": ("conflicting",),
    "cascading_changes": ("stale", "constraint_change", "missing"),
}
_FAULT_TYPES = ("missing", "stale", "conflicting", "constraint_change")


def _scenario(value: Scenario | dict[str, Any]) -> Scenario:
    """Normalize a scenario object or JSON mapping."""
    if isinstance(value, Scenario):
        scenario = value
    elif isinstance(value, dict):
        scenario = Scenario(
            name=str(value.get("name", value.get("scenario", "custom"))),
            severity=float(value.get("severity", 0.5)),
            config=dict(value.get("config", {})),
        )
    else:
        raise TypeError("scenario must be a Scenario or mapping")
    if not scenario.name.strip() or not 0 <= scenario.severity <= 1:
        raise ValueError("scenario name and severity are invalid")
    return scenario


def _fault_types(scenario: Scenario) -> tuple[str, ...]:
    """Select reproducible fault classes from the scenario name or config."""
    configured = scenario.config.get("fault_types")
    if configured is not None:
        if not isinstance(configured, list) or any(item not in _FAULT_TYPES for item in configured):
            raise ValueError("fault_types must contain supported fault names")
        return tuple(dict.fromkeys(configured))
    if scenario.name in _FAULTS_BY_SCENARIO:
        return _FAULTS_BY_SCENARIO[scenario.name]
    matched = tuple(kind for kind in _FAULT_TYPES if kind in scenario.name.casefold())
    return matched or _FAULT_TYPES


def _events(scenario: Scenario, seed: int) -> tuple[list[dict[str, Any]], GroundTruth]:
    """Create synthetic observations and hidden fault labels from one local RNG."""
    rng = random.Random(seed)
    count = int(scenario.config.get("event_count", 100))
    if not 1 <= count <= 10_000:
        raise ValueError("event_count must be in [1, 10000]")
    fault_types = _fault_types(scenario)
    fault_count = min(count, round(count * scenario.severity)) if fault_types else 0
    fault_positions = set(rng.sample(range(count), fault_count))
    events: list[dict[str, Any]] = []
    labels: list[dict[str, str]] = []
    for index in range(count):
        event_id = f"event-{index:05d}"
        hour = index
        value = round(rng.uniform(1.0, 100.0), 3)
        event: dict[str, Any] = {
            "event_id": event_id,
            "asset_id": f"resource-{index % 12:02d}",
            "event_hour": hour,
            "observed_at_hour": hour,
            "capacity_mw": value,
        }
        if index in fault_positions:
            fault_type = fault_types[index % len(fault_types)]
            labels.append({"event_id": event_id, "fault_type": fault_type})
            if fault_type == "missing":
                event["capacity_mw"] = None
            elif fault_type == "stale":
                event["observed_at_hour"] = max(0, hour - rng.randint(1, 24))
            elif fault_type == "conflicting":
                event["source_values"] = [value, round(value + rng.uniform(1, 10), 3)]
            elif fault_type == "constraint_change":
                event["constraint_change"] = {
                    "old_limit": round(value, 3),
                    "new_limit": round(value * rng.uniform(0.1, 0.9), 3),
                }
        events.append(event)
    return events, GroundTruth(tuple(labels))


def run(
    scenario: Scenario | dict[str, Any],
    seed: int,
    system: SystemUnderTest | None = None,
) -> RunResult:
    """Run seeded synthetic faults through a system and return hidden labels/results.

    Args:
        scenario: Scenario object or JSON-compatible scenario configuration.
        seed: Non-negative reproducibility seed.
        system: Optional implementation of ingest/detect/plan/verify. A deterministic
            in-process system is used when omitted by the API service.

    Returns:
        Scenario events, labels, detections, feasibility, and deterministic recovery time.

    Raises:
        TypeError: If the scenario or its config has an invalid shape.
        ValueError: If scenario values, fault types, or event count are invalid.
    """
    if seed < 0:
        raise ValueError("seed must be non-negative")
    normalized = _scenario(scenario)
    events, labels = _events(normalized, seed)
    subject = system or SyntheticSystem()
    failed = False
    feasible = False
    try:
        subject.ingest(events)
        detections = tuple(sorted(set(str(item) for item in subject.detect())))
        plan = subject.plan()
        feasible = bool(subject.verify(plan))
    except Exception:
        detections = ()
        failed = True
    positive_count = len(labels.labels)
    hit_count = len(set(detections) & {label["event_id"] for label in labels.labels})
    recovery_time = round(
        max(0, positive_count - hit_count) * 0.5 + positive_count * (1.0 - normalized.severity),
        3,
    )
    return RunResult(
        scenario=normalized.name,
        seed=seed,
        events=tuple(events),
        labels=labels,
        detections=detections,
        feasible=feasible,
        failed=failed,
        recovery_time=recovery_time,
    )
