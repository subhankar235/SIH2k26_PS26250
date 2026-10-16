"""Small timezone-safe UTC helpers shared by services and tests."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current instant as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 string and normalize it to aware UTC.

    Naive ISO timestamps follow ingestion convention and are interpreted as UTC.

    Raises:
        TypeError: If ``value`` is not a string.
        ValueError: If it is not an ISO-8601 datetime.
    """
    if not isinstance(value, str):
        raise TypeError("ISO timestamp must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("ISO timestamp must not be empty")
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"Invalid ISO-8601 datetime: {value!r}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
