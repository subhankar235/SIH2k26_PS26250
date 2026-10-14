"""Resolve API-facing service entry points without embedding business logic in routers."""

from __future__ import annotations

from importlib import import_module
from typing import Any, TypeVar, cast

from backend.app.core.exceptions import ServiceUnavailableError

T = TypeVar("T")


def dispatch(
    module_name: str,
    function_name: str,
    *args: Any,
    response_type: type[T] | None = None,
    **kwargs: Any,
) -> T:
    """Invoke a configured domain service entry point.

    Args:
        module_name: Fully qualified service module.
        function_name: Public service function to invoke.
        *args: Positional arguments passed to the service.
        response_type: Optional result type marker for static type inference.
        **kwargs: Keyword arguments passed to the service.

    Returns:
        The result returned by the domain service.

    Raises:
        ServiceUnavailableError: If the requested service function is not implemented.
    """
    try:
        module = import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name and (module_name == error.name or module_name.startswith(f"{error.name}.")):
            raise ServiceUnavailableError(
                f"Service {module_name}.{function_name} is not available"
            ) from error
        raise

    function = getattr(module, function_name, None)
    if not callable(function):
        raise ServiceUnavailableError(f"Service {module_name}.{function_name} is not available")
    _ = response_type
    return cast(T, function(*args, **kwargs))
