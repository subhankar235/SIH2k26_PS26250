"""Transactional idempotency support for create and solve operations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, TypeVar, cast

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.exceptions import ConflictError
from backend.app.db.models.idempotency import IdempotencyRecord

T = TypeVar("T")


def request_fingerprint(body: object) -> str:
    """Return a deterministic SHA-256 fingerprint for a JSON-compatible body.

    Args:
        body: Request body to canonicalize and hash.

    Returns:
        A lowercase hexadecimal SHA-256 digest.

    Raises:
        TypeError: If the body cannot be represented as JSON.
        ValueError: If the body contains a non-finite JSON number.
    """
    canonical = json.dumps(
        jsonable_encoder(body),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def execute_idempotently(
    db: Session,
    key: str | None,
    request_body: object,
    operation: Callable[[], T],
    result_model: type[BaseModel] | None = None,
) -> T:
    """Execute an operation once per key and request body in the current transaction.

    Args:
        db: Database session used for the idempotency row and operation.
        key: Optional idempotency key; None executes the operation without caching.
        request_body: Request payload used to detect key reuse with a different body.
        operation: Side-effecting operation to run for a new key.
        result_model: Optional Pydantic model used to reconstruct a cached response.

    Returns:
        The operation result, or its previously stored response for a replay.

    Raises:
        ConflictError: If a key is reused with a different body or has no completed result.
    """
    if key is None:
        return operation()

    normalized_key = key.strip()
    if not normalized_key or len(normalized_key) > 255:
        raise ConflictError("Idempotency key must contain 1 to 255 characters")

    fingerprint = request_fingerprint(request_body)
    existing = db.get(IdempotencyRecord, normalized_key)
    if existing is not None:
        return cast(T, _replay(existing, fingerprint, result_model))

    try:
        # The unique key is claimed before the operation, within the same transaction.
        # Concurrent requests with this key block at flush and then replay the committed row.
        with db.begin_nested():
            record = IdempotencyRecord(
                key=normalized_key,
                request_hash=fingerprint,
                response_payload={"_pending": True},
            )
            db.add(record)
            db.flush()
            result = operation()
            record.response_payload = {"_result": jsonable_encoder(result)}
            db.flush()
        return result
    except IntegrityError:
        # A concurrent transaction won the unique-key race. Its result is now authoritative.
        existing = db.get(IdempotencyRecord, normalized_key)
        if existing is None:
            raise
        return cast(T, _replay(existing, fingerprint, result_model))


def _replay(
    record: IdempotencyRecord,
    fingerprint: str,
    result_model: type[BaseModel] | None,
) -> Any:
    """Validate a stored request fingerprint and reconstruct its response."""
    if record.request_hash != fingerprint:
        raise ConflictError("Idempotency-Key was already used with a different request body")
    stored = record.response_payload
    if not isinstance(stored, dict) or "_result" not in stored:
        raise ConflictError("Idempotent request has no completed response")
    result = stored["_result"]
    if result_model is not None:
        return result_model.model_validate(result)
    return result
