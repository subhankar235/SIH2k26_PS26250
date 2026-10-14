"""Common API response schemas."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class APIModel(BaseModel):
    """Base Pydantic v2 contract with ORM attribute support."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class Page(APIModel, Generic[T]):
    """Represent a page of results with its pagination metadata."""

    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(gt=0)
    offset: int = Field(ge=0)


class PaginationParams(APIModel):
    """Represent validated pagination query parameters."""

    limit: int = Field(default=50, gt=0)
    offset: int = Field(default=0, ge=0)


class ErrorResponse(APIModel):
    """Represent a structured API error response."""

    code: str
    message: str
    details: dict[str, object] | None = None


class IdResponse(APIModel):
    """Represent a response containing a resource identifier."""

    id: str
