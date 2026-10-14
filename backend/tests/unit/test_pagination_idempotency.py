"""Tests for shared pagination and idempotency contracts."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core.deps import get_idempotency_key, get_pagination
from backend.app.core.exceptions import ConflictError, RequestValidationFailed
from backend.app.db.base import Base
from backend.app.db.models.idempotency import IdempotencyRecord
from backend.app.schemas.common import ErrorResponse, Page, PaginationParams
from backend.app.services.idempotency import execute_idempotently, request_fingerprint


class SampleResponse(BaseModel):
    value: int


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_page_contract_and_validation() -> None:
    page = Page[int](items=[1, 2], total=8, limit=2, offset=4)

    assert page.model_dump() == {"items": [1, 2], "total": 8, "limit": 2, "offset": 4}
    with pytest.raises(ValueError):
        Page[int](items=[], total=0, limit=0, offset=0)


def test_common_error_response_shape() -> None:
    response = ErrorResponse(
        code="NOT_FOUND", message="Decision not found", details={"id": "example"}
    )

    assert response.model_dump() == {
        "code": "NOT_FOUND",
        "message": "Decision not found",
        "details": {"id": "example"},
    }


def test_pagination_dependency_defaults_and_values() -> None:
    assert get_pagination() == PaginationParams(limit=50, offset=0)
    assert get_pagination(limit=10, offset=20) == PaginationParams(limit=10, offset=20)


def test_idempotency_header_is_optional_trimmed_and_validated() -> None:
    assert get_idempotency_key() is None
    assert get_idempotency_key("  request-1  ") == "request-1"
    with pytest.raises(RequestValidationFailed):
        get_idempotency_key("  ")
    with pytest.raises(RequestValidationFailed):
        get_idempotency_key("x" * 256)


def test_request_fingerprint_is_independent_of_mapping_order() -> None:
    assert request_fingerprint({"a": 1, "b": 2}) == request_fingerprint({"b": 2, "a": 1})


def test_idempotent_replay_returns_stored_result_without_rerunning(db: Session) -> None:
    calls = 0

    def operation() -> SampleResponse:
        nonlocal calls
        calls += 1
        return SampleResponse(value=42)

    first = execute_idempotently(
        db, "request-1", {"value": 42}, operation, result_model=SampleResponse
    )
    second = execute_idempotently(
        db, "request-1", {"value": 42}, operation, result_model=SampleResponse
    )

    assert first == second == SampleResponse(value=42)
    assert calls == 1
    assert db.query(IdempotencyRecord).count() == 1


def test_same_idempotency_key_with_different_body_conflicts(db: Session) -> None:
    execute_idempotently(db, "request-1", {"value": 42}, lambda: {"ok": True})

    with pytest.raises(ConflictError):
        execute_idempotently(db, "request-1", {"value": 43}, lambda: {"ok": False})


def test_failed_operation_does_not_leave_an_idempotency_record(db: Session) -> None:
    def fail() -> dict[str, bool]:
        raise RuntimeError("operation failed")

    with pytest.raises(RuntimeError):
        execute_idempotently(db, "request-1", {"value": 1}, fail)

    result = execute_idempotently(db, "request-1", {"value": 1}, lambda: {"ok": True})
    assert result == {"ok": True}
    assert db.query(IdempotencyRecord).count() == 1
