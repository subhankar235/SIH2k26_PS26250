"""Core grid asset domain types."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GridAsset:
    """A measured grid asset used by API, simulation, and planning modules."""

    asset_id: str
    asset_type: str
    capacity_mw: float
    available: bool = True
