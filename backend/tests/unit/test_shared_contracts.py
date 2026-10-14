"""Tests for shared backend enums and error contracts."""

from __future__ import annotations

import pytest

from backend.app.core.enums import (
    AgentRunStatus,
    ApprovalDecision,
    FaultType,
    IssueClass,
    ScheduleStatus,
    SourceType,
    ValidityStatus,
    VerificationOutcome,
)
from backend.app.core.exceptions import (
    AirPowerError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    RequestValidationFailed,
    SolverInfeasible,
    VerificationFailed,
)


@pytest.mark.parametrize(
    ("enum_type", "members"),
    [
        (SourceType, ["resource", "crew", "availability", "weather", "constraint"]),
        (IssueClass, ["stale", "missing", "duplicate", "conflict"]),
        (ValidityStatus, ["verified", "stale", "invalidated", "uncertain"]),
        (VerificationOutcome, ["verified", "invalid", "uncertain"]),
        (
            ScheduleStatus,
            ["draft", "verified", "invalid", "uncertain", "approved", "rejected", "superseded"],
        ),
        (ApprovalDecision, ["approved", "rejected"]),
        (
            AgentRunStatus,
            ["pending", "running", "awaiting_approval", "completed", "failed", "escalated"],
        ),
        (FaultType, ["missing", "stale", "conflicting", "constraint_change"]),
    ],
)
def test_enum_values_match_shared_contract(enum_type: type, members: list[str]) -> None:
    assert [member.value for member in enum_type] == members


@pytest.mark.parametrize(
    ("error_type", "code", "http_status"),
    [
        (AirPowerError, "INTERNAL", 500),
        (NotFoundError, "NOT_FOUND", 404),
        (RequestValidationFailed, "VALIDATION_ERROR", 422),
        (ConflictError, "CONFLICT", 409),
        (VerificationFailed, "VERIFICATION_FAILED", 422),
        (SolverInfeasible, "INFEASIBLE", 422),
        (ForbiddenError, "FORBIDDEN", 403),
    ],
)
def test_error_metadata_and_context(
    error_type: type[AirPowerError], code: str, http_status: int
) -> None:
    details = {"id": "example"}
    error = error_type("Request failed", details)

    assert isinstance(error, AirPowerError)
    assert error.code == code
    assert error.http_status == http_status
    assert str(error) == "Request failed"
    assert error.message == "Request failed"
    assert error.details == details
