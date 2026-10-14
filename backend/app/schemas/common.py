"""Common API response schemas."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Represent a page of results with its pagination metadata."""

    model_config = ConfigDict(from_attributes=True)

    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(gt=0)
    offset: int = Field(ge=0)


class PaginationParams(BaseModel):
    """Represent validated pagination query parameters."""

    model_config = ConfigDict(from_attributes=True)

    limit: int = Field(default=50, gt=0)
    offset: int = Field(default=0, ge=0)


class ErrorResponse(BaseModel):
    """Represent a structured API error response."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    message: str
    details: dict[str, object] | None = None


class IdResponse(BaseModel):
    """Represent a response containing a resource identifier."""

    model_config = ConfigDict(from_attributes=True)

    id: str
