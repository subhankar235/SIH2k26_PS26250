"""Feasibility helpers for grid dispatch plans."""

def reserve_margin(generation_mw: float, demand_mw: float) -> float:
    """Compute generation reserve as a fraction of demand."""
    if demand_mw <= 0:
        raise ValueError("demand_mw must be positive")
    return (generation_mw - demand_mw) / demand_mw


def meets_reserve_target(generation_mw: float, demand_mw: float, target: float) -> bool:
    """Return whether available generation satisfies the reserve target."""
    return reserve_margin(generation_mw, demand_mw) >= target
