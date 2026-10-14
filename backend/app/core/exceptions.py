"""Shared application exception hierarchy and HTTP error metadata."""

from __future__ import annotations


class AirPowerError(Exception):
    """Base exception for expected application errors."""

    code = "INTERNAL"
    http_status = 500

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        """Create an application error with an optional structured context.

        Args:
            message: Human-readable error description.
            details: Optional structured context safe to return to API clients.

        Returns:
            None.

        Raises:
            None.
        """
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AirPowerError):
    """Indicate that a requested resource does not exist."""

    code = "NOT_FOUND"
    http_status = 404


class RequestValidationFailed(AirPowerError):
    """Indicate that a request failed application-level validation."""

    code = "VALIDATION_ERROR"
    http_status = 422


class ConflictError(AirPowerError):
    """Indicate that a request conflicts with the current resource state."""

    code = "CONFLICT"
    http_status = 409


class VerificationFailed(AirPowerError):
    """Indicate that verification rejected a requested state transition."""

    code = "VERIFICATION_FAILED"
    http_status = 422


class SolverInfeasible(AirPowerError):
    """Indicate that no feasible solution could be found."""

    code = "INFEASIBLE"
    http_status = 422


class SolverOutcomeError(AirPowerError):
    """Indicate that the solver returned no usable schedule."""

    code = "SOLVER_NO_SOLUTION"
    http_status = 422


class ForbiddenError(AirPowerError):
    """Indicate that the actor is not allowed to perform an operation."""

    code = "FORBIDDEN"
    http_status = 403


class ServiceUnavailableError(AirPowerError):
    """Indicate that an API operation has no configured service implementation."""

    code = "SERVICE_UNAVAILABLE"
    http_status = 503
