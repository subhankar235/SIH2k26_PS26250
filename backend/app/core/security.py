"""API-key authentication and role dependencies."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import Depends, Header
from pydantic import BaseModel, ConfigDict

from backend.app.core.config import get_settings
from backend.app.core.exceptions import ForbiddenError


class Actor(BaseModel):
    """Identify an authenticated API actor and its role."""

    model_config = ConfigDict(frozen=True)

    id: str
    role: Literal["viewer", "analyst", "approver", "admin"]


def get_actor(x_api_key: Annotated[str, Header()]) -> Actor:
    """Authenticate a request using a configured API key.

    Args:
        x_api_key: Credential from the `X-API-Key` request header.

    Returns:
        The actor configured for this API key.

    Raises:
        ForbiddenError: If the key is unknown or its actor data is invalid.
    """
    actor_data = get_settings().api_keys.get(x_api_key)
    if actor_data is None:
        raise ForbiddenError("Invalid API key")
    try:
        return Actor.model_validate(actor_data)
    except ValueError as error:
        raise ForbiddenError("API key has invalid actor configuration") from error


def require_role(*roles: str) -> Callable[..., Actor]:
    """Create a dependency that requires one of the specified actor roles.

    Args:
        roles: Roles allowed to access the dependency-protected endpoint.

    Returns:
        A FastAPI dependency that returns the authenticated actor.

    Raises:
        ValueError: If no roles are supplied or a role is unsupported.
    """
    valid_roles = {"viewer", "analyst", "approver", "admin"}
    if not roles or any(role not in valid_roles for role in roles):
        raise ValueError("require_role needs one or more supported roles")

    def dependency(actor: Annotated[Actor, Depends(get_actor)]) -> Actor:
        if actor.role not in roles:
            raise ForbiddenError("Actor role is not allowed", {"required_roles": list(roles)})
        return actor

    return dependency
