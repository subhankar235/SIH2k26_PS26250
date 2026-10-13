"""Typed API response models."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str


class GridSummary(BaseModel):
    total_assets: int = Field(ge=0)
    healthy_assets: int = Field(ge=0)
    active_alerts: int = Field(ge=0)
    renewable_share: float = Field(ge=0, le=1)
    demand_mw: float = Field(ge=0)
    reserve_margin: float = Field(ge=0, le=1)
