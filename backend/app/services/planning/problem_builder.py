"""Build validated optimizer inputs from API requests and versioned database data."""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import asdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.exceptions import ConflictError, NotFoundError, RequestValidationFailed
from backend.app.db.models.claim import Issue
from backend.app.db.models.forecast import Forecast
from backend.app.db.models.record import Record
from backend.app.schemas.planning import ProblemIn
from backend.app.services.validity.input_versions import current_input_version
from optimisation.models.problem import Policy, Precedence, Problem, Resource, Task


def _positive_int(value: object, field: str, *, minimum: int = 1) -> int:
    """Parse an integer-valued scheduling field without accepting booleans."""
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise RequestValidationFailed(
            f"{field} must be an integer >= {minimum}", {"field": field}
        )
    return value


def _nonnegative_float(value: object, field: str) -> float:
    """Parse a finite non-negative objective or cost value."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise RequestValidationFailed(f"{field} must be numeric", {"field": field})
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise RequestValidationFailed(f"{field} must be finite and non-negative", {"field": field})
    return parsed


def _record_id(item: dict[str, Any]) -> uuid.UUID | None:
    """Parse an optional source-record reference from a task/resource request."""
    raw_id = item.get("record_id")
    if raw_id is None:
        return None
    try:
        return uuid.UUID(str(raw_id))
    except (TypeError, ValueError) as error:
        raise RequestValidationFailed(
            "record_id must be a UUID", {"record_id": str(raw_id)}
        ) from error


def _invalid_record_ids(db: Session) -> set[uuid.UUID]:
    """Find records with persisted invalid flags or an explicit open invalid issue."""
    invalid = {
        record.id
        for record in db.scalars(select(Record))
        if "invalid" in record.flags or record.superseded_by is not None
    }
    for issue in db.scalars(select(Issue).where(Issue.status == "open")):
        record_id = issue.details.get("record_id")
        issue_flags = issue.details.get("flags") or []
        explicitly_invalid = issue.details.get("invalid") is True or (
            (isinstance(issue_flags, list) and "invalid" in issue_flags)
            or issue_flags == "invalid"
        )
        if record_id and explicitly_invalid:
            try:
                invalid.add(uuid.UUID(str(record_id)))
            except ValueError:
                continue
    return invalid


def _allow_invalid_records(req: ProblemIn) -> bool:
    """Read an explicit global allow-invalid policy from request policy entries."""
    for policy in req.policies:
        if policy.get("allow_invalid_records") is True:
            return True
        if policy.get("name") == "allow_invalid_records" and policy.get("enabled", True) is True:
            return True
    return False


def _window_for_task(windows: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Return per-task window configuration normalized from supported JSON forms."""
    task_windows = windows.get("tasks", {})
    if not isinstance(task_windows, dict):
        raise RequestValidationFailed("windows.tasks must be an object")
    value = windows.get(task_id, task_windows.get(task_id, {}))
    if isinstance(value, dict):
        return value
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return {"earliest": value[0], "latest": value[1]}
    if value in (None, {}):
        return {}
    raise RequestValidationFailed(
        "task window must be an object or a two-element range", {"task_id": task_id}
    )


def _resource_windows(
    raw: dict[str, Any], horizon: int, global_windows: dict[str, Any]
) -> list[tuple[int, int]]:
    """Normalize resource availability into ordered half-open integer windows."""
    configured = raw.get("available", raw.get("availability"))
    if configured is None:
        global_resources = global_windows.get("resources", {})
        if not isinstance(global_resources, dict):
            raise RequestValidationFailed("windows.resources must be an object")
        configured = global_resources.get(str(raw.get("id", raw.get("resource_id"))))
    if configured is None:
        return [(0, horizon)]
    if not isinstance(configured, list):
        raise RequestValidationFailed("resource availability must be a list")
    result: list[tuple[int, int]] = []
    for interval in configured:
        if isinstance(interval, dict):
            start_value, end_value = interval.get("start"), interval.get("end")
        elif isinstance(interval, (list, tuple)) and len(interval) == 2:
            start_value, end_value = interval
        else:
            raise RequestValidationFailed("resource availability entries must be [start, end]")
        start = _positive_int(start_value, "availability start", minimum=0)
        end = _positive_int(end_value, "availability end")
        if end <= start or end > horizon:
            raise RequestValidationFailed(
                "resource availability must satisfy 0 <= start < end <= horizon",
                {"start": start, "end": end, "horizon": horizon},
            )
        result.append((start, end))
    return sorted(set(result))


def _forecast_buffer(forecast: Forecast) -> tuple[float, dict[str, Any]]:
    """Compute a bounded relative duration buffer from persisted forecast intervals."""
    if not forecast.points:
        raise RequestValidationFailed("forecast has no points to derive planning uncertainty")
    configured_scale = forecast.calibration_meta.get("target_scale")
    try:
        target_scale = float(configured_scale) if configured_scale is not None else 0.0
    except (TypeError, ValueError) as error:
        raise RequestValidationFailed("forecast target_scale is invalid") from error
    widths: list[float] = []
    for point in forecast.points:
        try:
            mean = float(point["mean"])
            lower = float(point["lower"])
            upper = float(point["upper"])
        except (KeyError, TypeError, ValueError) as error:
            raise RequestValidationFailed("forecast point is missing interval values") from error
        if (
            not all(math.isfinite(value) for value in (mean, lower, upper))
            or lower > mean
            or mean > upper
        ):
            raise RequestValidationFailed("forecast contains an invalid prediction interval")
        width = upper - lower
        scale = max(abs(mean), target_scale)
        relative_width = width / scale if scale > 0 else (0.0 if width == 0 else 1.0)
        widths.append(relative_width)
    buffer_fraction = min(10.0, max(widths, default=0.0))
    return buffer_fraction, {
        "forecast_id": str(forecast.id),
        "forecast_version": forecast.version,
        "target": forecast.target,
        "max_relative_interval_width": max(widths, default=0.0),
        "duration_buffer_fraction": buffer_fraction,
    }


def build_problem(db: Session, req: ProblemIn, forecast_id: uuid.UUID | None = None) -> Problem:
    """Convert a request to optimizer dataclasses and capture source versions.

    Args:
        db: Active synchronous database session.
        req: API problem request with tasks, resources, windows, and policies.
        forecast_id: Optional persisted forecast whose uncertainty widens durations.

    Returns:
        Validated deterministic optimizer problem and exact input-version references.

    Raises:
        ConflictError: If referenced records or forecasts are stale.
        NotFoundError: If a referenced record or forecast does not exist.
        RequestValidationFailed: If task/resource/window/policy values are invalid.
    """
    forecast_id = forecast_id or req.forecast_id
    window_config = req.windows
    allow_invalid = _allow_invalid_records(req)
    invalid_ids = set() if allow_invalid else _invalid_record_ids(db)
    task_rows: list[tuple[dict[str, Any], dict[str, Any], uuid.UUID | None]] = []
    for raw in req.tasks:
        task_id = str(raw.get("id", raw.get("task_id", ""))).strip()
        if not task_id:
            raise RequestValidationFailed("Every task needs a non-empty id")
        task_rows.append((raw, _window_for_task(window_config, task_id), _record_id(raw)))
    request_task_ids = [
        str(raw.get("id", raw.get("task_id"))).strip() for raw, _, _ in task_rows
    ]
    if len(set(request_task_ids)) != len(request_task_ids):
        raise RequestValidationFailed("Task ids must be unique")

    resource_rows = [(raw, _record_id(raw)) for raw in req.resources]
    referenced_ids = {record_id for _, _, record_id in task_rows if record_id is not None}
    referenced_ids.update(record_id for _, record_id in resource_rows if record_id is not None)
    records: dict[uuid.UUID, Record] = {}
    for record_id in referenced_ids:
        record = db.get(Record, record_id)
        if record is None:
            raise NotFoundError("Planning record not found", {"record_id": str(record_id)})
        records[record_id] = record

    kept_tasks = [
        (raw, window, record_id)
        for raw, window, record_id in task_rows
        if allow_invalid
        or raw.get("allow_invalid") is True
        or record_id is None
        or record_id not in invalid_ids
    ]
    kept_resources = [
        (raw, record_id)
        for raw, record_id in resource_rows
        if allow_invalid
        or raw.get("allow_invalid") is True
        or record_id is None
        or record_id not in invalid_ids
    ]
    if not kept_tasks:
        raise RequestValidationFailed("No schedulable tasks remain after invalid-record filtering")
    if not kept_resources:
        raise RequestValidationFailed("At least one schedulable resource is required")

    forecast: Forecast | None = None
    buffer_fraction = 0.0
    forecast_meta: dict[str, Any] = {}
    if forecast_id is not None:
        forecast = db.get(Forecast, forecast_id)
        if forecast is None:
            raise NotFoundError("Forecast not found", {"id": str(forecast_id)})
        latest_version = current_input_version(db, "forecast", forecast.id)
        if latest_version != forecast.version:
            raise ConflictError(
                "Planning forecast is not the latest version",
                {"forecast_id": str(forecast.id), "latest_version": latest_version},
            )
        buffer_fraction, forecast_meta = _forecast_buffer(forecast)

    durations = {
        str(raw.get("id", raw.get("task_id"))).strip(): math.ceil(
            _positive_int(raw.get("duration"), "task duration") * (1.0 + buffer_fraction)
        )
        for raw, _, _ in kept_tasks
    }

    explicit_horizon = window_config.get("horizon")
    if explicit_horizon is not None:
        horizon = _positive_int(explicit_horizon, "horizon")
    else:
        endpoints: list[int] = []
        for raw, per_task_window, _ in kept_tasks:
            task_id = str(raw.get("id", raw.get("task_id"))).strip()
            duration = durations[task_id]
            latest = raw.get(
                "latest",
                per_task_window.get(
                    "latest",
                    per_task_window.get(
                        "end", window_config.get("latest", window_config.get("end"))
                    ),
                ),
            )
            if latest is not None:
                endpoints.append(_positive_int(latest, "task latest", minimum=0) + duration)
        for raw, _ in kept_resources:
            for interval in raw.get("available", raw.get("availability", [])):
                if isinstance(interval, dict):
                    endpoint = interval.get("end")
                elif isinstance(interval, (list, tuple)) and len(interval) == 2:
                    endpoint = interval[1]
                else:
                    continue
                endpoints.append(_positive_int(endpoint, "availability end"))
        endpoints.append(sum(durations.values()))
        horizon = max(endpoints, default=1)
        if horizon < 1:
            raise RequestValidationFailed("Could not infer a positive scheduling horizon")

    tasks: list[Task] = []
    for raw, per_task_window, _ in kept_tasks:
        task_id = str(raw.get("id", raw.get("task_id"))).strip()
        duration = durations[task_id]
        earliest = _positive_int(
            raw.get(
                "earliest",
                per_task_window.get(
                    "earliest",
                    per_task_window.get(
                        "start", window_config.get("earliest", window_config.get("start", 0))
                    ),
                ),
            ),
            f"task {task_id} earliest",
            minimum=0,
        )
        latest = _positive_int(
            raw.get(
                "latest",
                per_task_window.get(
                    "latest",
                    per_task_window.get(
                        "end",
                        window_config.get("latest", window_config.get("end", horizon - duration)),
                    ),
                ),
            ),
            f"task {task_id} latest",
            minimum=0,
        )
        if latest < earliest:
            raise RequestValidationFailed(
                "Task latest start must not precede earliest start", {"task_id": task_id}
            )
        resource_type = str(raw.get("resource_type", "any")).strip()
        if not resource_type:
            raise RequestValidationFailed(
                "Task resource_type must not be empty", {"task_id": task_id}
            )
        priority = _positive_int(raw.get("priority", 1), f"task {task_id} priority", minimum=0)
        due_raw = raw.get("due")
        due = (
            _positive_int(due_raw, f"task {task_id} due", minimum=0)
            if due_raw is not None
            else None
        )
        tasks.append(Task(task_id, duration, resource_type, earliest, latest, priority, due))

    resources: list[Resource] = []
    for raw, _ in kept_resources:
        resource_id = str(raw.get("id", raw.get("resource_id", ""))).strip()
        resource_type = str(raw.get("type", raw.get("resource_type", ""))).strip()
        if not resource_id or not resource_type:
            raise RequestValidationFailed("Every resource needs a non-empty id and type")
        capacity = _positive_int(raw.get("capacity", 1), f"resource {resource_id} capacity")
        cost = _nonnegative_float(raw.get("cost_per_unit", 0.0), "resource cost_per_unit")
        resources.append(
            Resource(
                id=resource_id,
                type=resource_type,
                capacity=capacity,
                available=_resource_windows(raw, horizon, window_config),
                cost_per_unit=cost,
            )
        )
    if len({resource.id for resource in resources}) != len(resources):
        raise RequestValidationFailed("Resource ids must be unique")

    precedence: list[Precedence] = []
    task_ids = {task.id for task in tasks}
    for raw in req.precedence:
        before, after = raw.get("before"), raw.get("after")
        if not isinstance(before, str) or not isinstance(after, str):
            raise RequestValidationFailed("Precedence entries need before and after task ids")
        if before not in task_ids or after not in task_ids or before == after:
            raise RequestValidationFailed("Precedence references unknown or identical tasks")
        gap = _positive_int(raw.get("min_gap", 0), "precedence min_gap", minimum=0)
        precedence.append(Precedence(before, after, gap))

    policies: list[Policy] = []
    for raw in req.policies:
        if raw.get("name") == "allow_invalid_records" or "allow_invalid_records" in raw:
            continue
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise RequestValidationFailed("Every planning policy needs a name")
        params = raw.get("params", {})
        if not isinstance(params, dict):
            raise RequestValidationFailed("Policy params must be an object", {"policy": name})
        policies.append(Policy(name, params))

    objectives = {
        name: _nonnegative_float(value, f"objective {name}")
        for name, value in req.objectives.items()
    }
    input_refs: dict[tuple[str, uuid.UUID], dict[str, Any]] = {}
    retained_record_ids = {
        record_id
        for _, _, record_id in kept_tasks
        if record_id is not None
    } | {record_id for _, record_id in kept_resources if record_id is not None}
    for record_id in retained_record_ids:
        record = records[record_id]
        latest_version = current_input_version(db, "record", record_id)
        if latest_version != record.version:
            raise ConflictError(
                "Planning record is not the latest version",
                {
                    "record_id": str(record_id),
                    "record_version": record.version,
                    "latest_version": latest_version,
                },
            )
        input_refs[("record", record_id)] = {
            "input_type": "record",
            "input_id": str(record.id),
            "input_version": record.version,
        }
    if forecast is not None:
        input_refs[("forecast", forecast.id)] = {
            "input_type": "forecast",
            "input_id": str(forecast.id),
            "input_version": forecast.version,
        }
    return Problem(
        tasks=tasks,
        resources=resources,
        precedence=precedence,
        policies=policies,
        horizon=horizon,
        objectives=objectives,
        input_versions=[
            input_refs[key]
            for key in sorted(input_refs, key=lambda item: (item[0], str(item[1])))
        ],
        forecast_meta=forecast_meta,
    )


def problem_hash(p: Problem) -> str:
    """Hash a canonical representation of a normalized scheduling problem.

    Args:
        p: Fully normalized scheduling problem.

    Returns:
        Lowercase SHA-256 hex digest stable across process runs.
    """
    payload = asdict(p)
    payload["resources"] = sorted(payload["resources"], key=lambda row: row["id"])
    payload["tasks"] = sorted(payload["tasks"], key=lambda row: row["id"])
    payload["precedence"] = sorted(
        payload["precedence"], key=lambda row: (row["before"], row["after"], row["min_gap"])
    )
    payload["policies"] = sorted(
        payload["policies"],
        key=lambda row: (
            row["name"],
            json.dumps(row["params"], sort_keys=True, separators=(",", ":"), allow_nan=False),
        ),
    )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def input_assignment_map(req: ProblemIn, problem: Problem) -> dict[str, dict[str, Any]]:
    """Capture source-to-task/resource provenance for conservative incremental replans."""
    valid_input_ids = {str(item["input_id"]) for item in problem.input_versions}
    mappings: dict[str, dict[str, Any]] = {}

    def mapping_for(raw_id: object) -> dict[str, Any] | None:
        try:
            input_id = str(uuid.UUID(str(raw_id)))
        except (TypeError, ValueError):
            return None
        if input_id not in valid_input_ids:
            return None
        return mappings.setdefault(
            input_id, {"task_ids": [], "resource_ids": [], "global": False}
        )

    valid_tasks = {task.id for task in problem.tasks}
    valid_resources = {resource.id for resource in problem.resources}
    for raw_task in req.tasks:
        task_id = str(raw_task.get("id", raw_task.get("task_id", ""))).strip()
        if task_id not in valid_tasks:
            continue
        mapping = mapping_for(raw_task.get("record_id"))
        if mapping is not None and task_id not in mapping["task_ids"]:
            mapping["task_ids"].append(task_id)
    for raw_resource in req.resources:
        resource_id = str(raw_resource.get("id", raw_resource.get("resource_id", ""))).strip()
        if resource_id not in valid_resources:
            continue
        mapping = mapping_for(raw_resource.get("record_id"))
        if mapping is not None and resource_id not in mapping["resource_ids"]:
            mapping["resource_ids"].append(resource_id)

    forecast_id = req.forecast_id
    if forecast_id is not None and str(forecast_id) in valid_input_ids:
        mappings[str(forecast_id)] = {
            "task_ids": sorted(valid_tasks),
            "resource_ids": [],
            "global": True,
        }
    for mapping in mappings.values():
        mapping["task_ids"].sort()
        mapping["resource_ids"].sort()
    return mappings
