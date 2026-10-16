"""Deterministic diffs for versioned input references."""

from __future__ import annotations

from uuid import UUID

from backend.app.core.exceptions import RequestValidationFailed
from backend.app.schemas.validity import ChangeEvent, InputRef


def _index(inputs: dict[str, InputRef], label: str) -> dict[tuple[str, UUID], InputRef]:
    """Index input refs by their stable type/id identity and reject ambiguity."""
    indexed: dict[tuple[str, UUID], InputRef] = {}
    for ref in inputs.values():
        key = (ref.input_type, ref.input_id)
        previous = indexed.get(key)
        if previous is not None and previous.input_version != ref.input_version:
            raise RequestValidationFailed(
                f"{label} input references contain conflicting versions",
                {"input_type": ref.input_type, "input_id": str(ref.input_id)},
            )
        indexed[key] = ref
    return indexed


def diff_inputs(old: dict[str, InputRef], new: dict[str, InputRef]) -> list[ChangeEvent]:
    """Return input additions and version changes in stable identity order.

    Removed refs are not representable as ``ChangeEvent`` because a removal has no
    positive new version. Versioned inputs should be retired with a new tombstone
    version instead.

    Args:
        old: Previously recorded refs keyed by any caller-defined stable key.
        new: Current refs keyed by any caller-defined stable key.

    Returns:
        One event for each added ref or changed version, sorted by type and UUID.

    Raises:
        RequestValidationFailed: If either mapping is ambiguous or an input was
            physically removed instead of receiving a tombstone version.
    """
    old_by_identity = _index(old, "old")
    new_by_identity = _index(new, "new")
    removed = sorted(old_by_identity.keys() - new_by_identity.keys())
    if removed:
        input_type, input_id = removed[0]
        raise RequestValidationFailed(
            "Removed inputs must be represented by a new tombstone version",
            {"input_type": input_type, "input_id": str(input_id)},
        )

    changes: list[ChangeEvent] = []
    for key in sorted(new_by_identity, key=lambda item: (item[0], str(item[1]))):
        current = new_by_identity[key]
        previous = old_by_identity.get(key)
        if previous is not None and previous.input_version == current.input_version:
            continue
        if previous is not None and current.input_version < previous.input_version:
            raise RequestValidationFailed(
                "Input versions must increase",
                {
                    "input_type": current.input_type,
                    "input_id": str(current.input_id),
                    "old_version": previous.input_version,
                    "new_version": current.input_version,
                },
            )
        changes.append(
            ChangeEvent(
                input_type=current.input_type,
                input_id=current.input_id,
                old_version=previous.input_version if previous is not None else None,
                new_version=current.input_version,
            )
        )
    return changes
