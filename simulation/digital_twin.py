"""Minimal SimPy-based asset availability simulation."""

import simpy


def run_availability_simulation(hours: int = 24, repair_hours: float = 2.0) -> float:
    """Simulate a single outage followed by repair; return available fraction."""
    if hours <= 0 or repair_hours < 0:
        raise ValueError("hours must be positive and repair_hours non-negative")
    environment = simpy.Environment()
    unavailable_time = min(repair_hours, float(hours))
    environment.run(until=hours)
    return 1.0 - unavailable_time / hours
