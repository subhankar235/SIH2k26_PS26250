"""Deterministic stress-run quality and baseline metrics."""

from __future__ import annotations

from typing import Any

from simulation.runner.run_scenario import GroundTruth, RunResult


def _rates(result: RunResult, labels: GroundTruth, detections: set[str]) -> dict[str, float]:
    """Calculate detection, false-alarm, feasibility, failure, and recovery rates."""
    positive_ids = {item["event_id"] for item in labels.labels}
    all_ids = {str(event["event_id"]) for event in result.events}
    clean_ids = all_ids - positive_ids
    true_positive = len(detections & positive_ids)
    false_positive = len(detections & clean_ids)
    false_negative = len(positive_ids - detections)
    true_negative = len(clean_ids - detections)
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 1.0
    )
    recall = true_positive / len(positive_ids) if positive_ids else 1.0
    false_alarm_rate = false_positive / len(clean_ids) if clean_ids else 0.0
    return {
        "detection_precision": precision,
        "detection_recall": recall,
        "false_alarm_rate": false_alarm_rate,
        "failure_rate": 1.0 if result.failed else false_negative / len(all_ids) if all_ids else 0.0,
        "feasibility_rate": 1.0 if result.feasible and not result.failed else 0.0,
        "recovery_time": result.recovery_time,
        "true_positive": float(true_positive),
        "false_positive": float(false_positive),
        "false_negative": float(false_negative),
        "true_negative": float(true_negative),
    }


def compute(result: RunResult, labels: GroundTruth) -> dict[str, Any]:
    """Compute system metrics and a deterministic no-detection baseline.

    Args:
        result: Output of the simulation runner.
        labels: Hidden ground-truth fault labels.

    Returns:
        Flat primary metrics plus a nested baseline metric table.
    """
    system_metrics = _rates(result, labels, set(result.detections))
    baseline_result = RunResult(
        scenario=result.scenario,
        seed=result.seed,
        events=result.events,
        labels=labels,
        detections=(),
        feasible=False if labels.labels else result.feasible,
        failed=False,
        recovery_time=float(len(labels.labels)),
    )
    return {
        **system_metrics,
        "baselines": {"no_detection": _rates(baseline_result, labels, set())},
    }
