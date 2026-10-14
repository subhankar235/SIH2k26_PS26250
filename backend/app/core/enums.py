"""Shared enumerations used by backend contracts."""

from __future__ import annotations

try:
    from enum import StrEnum
except ImportError:  # Python 3.10 compatibility
    from enum import Enum

    class StrEnum(str, Enum):
        """Backport of Python 3.11's StrEnum for older runtimes."""


class SourceType(StrEnum):
    """Identify a source category for incoming records."""

    RESOURCE = "resource"
    CREW = "crew"
    AVAILABILITY = "availability"
    WEATHER = "weather"
    CONSTRAINT = "constraint"


class IssueClass(StrEnum):
    """Classify an evidence-quality issue."""

    STALE = "stale"
    MISSING = "missing"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"


class ValidityStatus(StrEnum):
    """Represent the current validity of a decision."""

    VERIFIED = "verified"
    STALE = "stale"
    INVALIDATED = "invalidated"
    UNCERTAIN = "uncertain"


class VerificationOutcome(StrEnum):
    """Represent the result of an independent verification check."""

    VERIFIED = "verified"
    INVALID = "invalid"
    UNCERTAIN = "uncertain"


class ScheduleStatus(StrEnum):
    """Represent the lifecycle state of a schedule."""

    DRAFT = "draft"
    VERIFIED = "verified"
    INVALID = "invalid"
    UNCERTAIN = "uncertain"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ApprovalDecision(StrEnum):
    """Represent a human approval decision."""

    APPROVED = "approved"
    REJECTED = "rejected"


class AgentRunStatus(StrEnum):
    """Represent the lifecycle state of an agent run."""

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"


class FaultType(StrEnum):
    """Classify a synthetic fault-injection operation."""

    MISSING = "missing"
    STALE = "stale"
    CONFLICTING = "conflicting"
    CONSTRAINT_CHANGE = "constraint_change"
