"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Header, Query
from sqlalchemy.orm import Session

from backend.app.core.exceptions import RequestValidationFailed
from backend.app.core.security import Actor, get_actor, require_role
from backend.app.schemas.common import PaginationParams

__all__ = [
    "Actor",
    "get_actor",
    "get_db",
    "get_idempotency_key",
    "get_pagination",
    "require_role",
]


def get_pagination(
    limit: Annotated[int, Query(gt=0)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginationParams:
    """Parse and validate standard pagination query parameters.

    Args:
        limit: Maximum number of records to return.
        offset: Number of records to skip.

    Returns:
        Validated pagination parameters.

    Raises:
        fastapi.exceptions.RequestValidationError: If either value is out of range.
    """
    return PaginationParams(limit=limit, offset=offset)


def get_db() -> Iterator[Session]:
    """Yield a database session and commit or roll back its transaction.

    Yields:
        A synchronous SQLAlchemy session.

    Raises:
        Exception: Re-raises any error after rolling back the transaction.
    """
    from backend.app.db.session import SessionLocal

    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str | None:
    """Read and validate the optional idempotency key request header.

    Args:
        idempotency_key: Value supplied in the `Idempotency-Key` header.

    Returns:
        A trimmed key, or None when the header was not supplied.

    Raises:
        RequestValidationFailed: If the supplied key is blank or too long.
    """
    if idempotency_key is None:
        return None
    key = idempotency_key.strip()
    if not key or len(key) > 255:
        raise RequestValidationFailed("Idempotency-Key must contain 1 to 255 characters")
    return key
