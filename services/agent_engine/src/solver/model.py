"""Domain data classes and data models for the Operations Research solver."""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass(frozen=True)
class Airframe:
    id: str
    capacity_kg: float
    max_range_km: float
    turnaround_mins: int = 45
    status: str = "available"  # "available", "maintenance", "unavailable"


@dataclass(frozen=True)
class Crew:
    id: str
    qualifications: tuple = ("transport",)
    duty_hours_left: float = 12.0
    status: str = "available"  # "available", "rest", "unavailable"


@dataclass(frozen=True)
class Corridor:
    id: str
    from_base: str
    to_base: str
    distance_km: float
    flight_time_mins: int
    threat_risk: float = 0.0  # 0.0 (safe) to 1.0 (hostile)
    weather_condition: str = "clear"  # "clear", "rain", "fog", "storm"


@dataclass(frozen=True)
class Mission:
    id: str
    origin_base: str
    dest_base: str
    payload_kg: float
    priority: int = 5  # 1 to 10
    deadline_slot: int = 4
    required_qualification: str = "transport"
    temperature_controlled: bool = False
    hazardous: bool = False
    max_threat_tolerance: float = 0.7


@dataclass
class Assignment:
    mission_id: str
    airframe_id: str
    crew_id: str
    corridor_id: str
    slot: int
    estimated_arrival_slot: int = 0
    threat_risk: float = 0.0


@dataclass
class SolverResult:
    status: str  # "optimal", "feasible", "infeasible"
    served_priority: int
    total_threat_risk: float
    assignments: List[Assignment] = field(default_factory=list)
    unserved: List[Dict[str, Any]] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

