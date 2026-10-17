"""Independent mathematical and constraint verifier for air operations schedules.

Validates that proposed schedules and assignments strictly adhere to physical,
logistical, crew duty, meteorological, and threat constraints without relying
on solver optimism.
"""

from typing import List, Dict, Any, Optional, Set
from .model import Airframe, Crew, Corridor, Mission, Assignment


class IndependentVerifier:
    """Rigorous independent checker for operational flight assignments."""

    @staticmethod
    def verify_assignment(
        assignment: Dict[str, Any],
        missions: Dict[str, Mission],
        airframes: Dict[str, Airframe],
        crews: Dict[str, Crew],
        corridors: Dict[str, Corridor],
        horizon: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Validate a single assignment against all domain physics and rules."""
        violations = []

        m_id = assignment.get("mission_id") or assignment.get("taskId")
        a_id = assignment.get("airframe_id") or assignment.get("resourceId")
        c_id = assignment.get("crew_id") or assignment.get("crewId")
        r_id = assignment.get("corridor_id") or assignment.get("corridorId")
        
        slot_raw = assignment.get("slot")
        if slot_raw is None:
            slot_raw = assignment.get("start")
        
        # Strict integer check: disallow bool, float, str, None, negative
        if slot_raw is None or isinstance(slot_raw, bool) or not isinstance(slot_raw, int) or slot_raw < 0:
            violations.append({
                "rule": "invalid_departure_slot",
                "message": f"Negative or invalid departure slot '{slot_raw}' for mission '{m_id}'",
                "refs": [m_id or "UNKNOWN"]
            })
            slot = 0
        else:
            slot = slot_raw

        mission = missions.get(m_id)
        if not mission:
            violations.append({
                "rule": "mission_existence",
                "message": f"Assigned mission '{m_id}' not found in registry",
                "refs": [m_id or "UNKNOWN"]
            })
            return violations

        if not a_id:
            violations.append({
                "rule": "missing_airframe",
                "message": f"Sortie mission '{m_id}' has no assigned airframe",
                "refs": [m_id or "UNKNOWN"]
            })
            airframe = None
        else:
            airframe = airframes.get(a_id)
            if not airframe:
                violations.append({
                    "rule": "airframe_existence",
                    "message": f"Assigned airframe '{a_id}' does not exist",
                    "refs": [a_id or "UNKNOWN"]
                })
            else:
                if airframe.status != "available":
                    violations.append({
                        "rule": "airframe_availability",
                        "message": f"Airframe '{a_id}' is currently {airframe.status}, cannot be assigned",
                        "refs": [a_id]
                    })
                if mission.payload_kg > airframe.capacity_kg:
                    violations.append({
                        "rule": "capacity_exceeded",
                        "message": f"Payload {mission.payload_kg} kg exceeds airframe '{a_id}' capacity {airframe.capacity_kg} kg",
                        "refs": [a_id, m_id]
                    })

        corridor = None
        if not r_id:
            violations.append({
                "rule": "missing_corridor",
                "message": f"Sortie mission '{m_id}' has no assigned corridor",
                "refs": [m_id or "UNKNOWN"]
            })
        else:
            corridor = corridors.get(r_id)
            if not corridor:
                violations.append({
                    "rule": "corridor_existence",
                    "message": f"Assigned corridor '{r_id}' does not exist",
                    "refs": [r_id or "UNKNOWN"]
                })
            else:
                if corridor.from_base != mission.origin_base or corridor.to_base != mission.dest_base:
                    violations.append({
                        "rule": "wrong_route",
                        "message": f"Corridor '{r_id}' ({corridor.from_base}->{corridor.to_base}) does not connect mission bases ({mission.origin_base}->{mission.dest_base})",
                        "refs": [r_id, m_id]
                    })
                if corridor.weather_condition == "storm":
                    violations.append({
                        "rule": "weather_safety",
                        "message": f"Corridor '{r_id}' is closed due to severe storm front",
                        "refs": [r_id]
                    })
                if corridor.threat_risk > mission.max_threat_tolerance:
                    violations.append({
                        "rule": "threat_exceeded",
                        "message": f"Corridor threat {corridor.threat_risk} exceeds mission tolerance {mission.max_threat_tolerance}",
                        "refs": [r_id, m_id]
                    })
                if airframe and corridor.distance_km > airframe.max_range_km:
                    violations.append({
                        "rule": "range_exceeded",
                        "message": f"Corridor distance {corridor.distance_km} km exceeds airframe range {airframe.max_range_km} km",
                        "refs": [a_id, r_id]
                    })

                # Travel duration & deadline
                flight_slots = max(1, (corridor.flight_time_mins + 59) // 60)
                arrival_slot = slot + flight_slots
                claimed_arrival = assignment.get("estimated_arrival_slot")
                if claimed_arrival is not None:
                    if claimed_arrival != arrival_slot or claimed_arrival < 0:
                        violations.append({
                            "rule": "forged_arrival_slot",
                            "message": f"Claimed arrival slot {claimed_arrival} does not match computed arrival slot {arrival_slot}",
                            "refs": [m_id or "UNKNOWN"]
                        })
                if arrival_slot > mission.deadline_slot:
                    violations.append({
                        "rule": "deadline_breach",
                        "message": f"Estimated arrival slot {arrival_slot} breaches mission deadline slot {mission.deadline_slot}",
                        "refs": [m_id, r_id]
                    })
                if horizon is not None and arrival_slot > horizon:
                    violations.append({
                        "rule": "horizon_breached",
                        "message": f"Estimated arrival slot {arrival_slot} exceeds operational horizon {horizon}",
                        "refs": [m_id, r_id]
                    })

        if not c_id:
            violations.append({
                "rule": "missing_crew",
                "message": f"Sortie mission '{m_id}' has no assigned crew",
                "refs": [m_id or "UNKNOWN"]
            })
        else:
            crew = crews.get(c_id)
            if not crew:
                violations.append({
                    "rule": "crew_existence",
                    "message": f"Assigned crew '{c_id}' does not exist",
                    "refs": [c_id]
                })
            else:
                if crew.status != "available":
                    violations.append({
                        "rule": "crew_availability",
                        "message": f"Crew '{c_id}' is in {crew.status} state, cannot fly",
                        "refs": [c_id]
                    })
                if mission.required_qualification not in crew.qualifications:
                    violations.append({
                        "rule": "crew_qualification",
                        "message": f"Crew '{c_id}' lacks required qualification '{mission.required_qualification}'",
                        "refs": [c_id, m_id]
                    })
                if corridor:
                    required_hours = corridor.flight_time_mins / 60.0
                    if crew.duty_hours_left < required_hours:
                        violations.append({
                            "rule": "duty_hours_exhausted",
                            "message": f"Flight time {required_hours:.1f}h exceeds crew '{c_id}' remaining duty {crew.duty_hours_left:.1f}h",
                            "refs": [c_id, r_id]
                        })

        return violations

    @classmethod
    def verify_schedule_bounds(cls, capacity: float, horizon: float) -> Optional[Dict[str, Any]]:
        """Verify solver parameters are physically valid."""
        if capacity <= 0 or horizon <= 0:
            return {
                "outcome": "invalid",
                "violations": [{
                    "rule": "invalid_operational_bounds",
                    "message": f"Capacity ({capacity}) and horizon ({horizon}) must be positive nonzero values",
                    "refs": ["PARAM-CAPACITY", "PARAM-HORIZON"]
                }],
                "uncertainty_flags": ["Negative or zero resource bounds requested"]
            }
        return None

    @classmethod
    def verify_complete_schedule(
        cls,
        assignments: List[Dict[str, Any]],
        missions: List[Mission],
        airframes: List[Airframe],
        crews: List[Crew],
        corridors: List[Corridor],
        capacity: float = 4,
        horizon: float = 8,
    ) -> Dict[str, Any]:
        """Perform full multi-axis independent verification of an entire schedule."""
        bounds_check = cls.verify_schedule_bounds(capacity, horizon)
        if bounds_check:
            return bounds_check

        m_dict = {m.id: m for m in missions}
        a_dict = {a.id: a for a in airframes}
        c_dict = {c.id: c for c in crews}
        r_dict = {r.id: r for r in corridors}

        all_violations = []
        assigned_missions: Set[str] = set()
        assigned_airframes: Set[str] = set()
        assigned_crews: Set[str] = set()
        corridor_slot_occupancy: Set[tuple] = set()

        if not assignments:
            all_violations.append({
                "rule": "no_assignments",
                "message": "Schedule contains zero mission assignments",
                "refs": []
            })

        for a in assignments:
            violations = cls.verify_assignment(a, m_dict, a_dict, c_dict, r_dict, horizon=horizon)
            all_violations.extend(violations)

            # Mission contention check (a mission cannot be flown twice)
            mission_id = a.get("mission_id") or a.get("taskId")
            if mission_id:
                if mission_id in assigned_missions:
                    all_violations.append({
                        "rule": "duplicate_mission",
                        "message": f"Mission '{mission_id}' is assigned to multiple concurrent sorties",
                        "refs": [mission_id]
                    })
                assigned_missions.add(mission_id)

            # Contention checks
            airframe_id = a.get("airframe_id") or a.get("resourceId")
            if airframe_id:
                if airframe_id in assigned_airframes:
                    all_violations.append({
                        "rule": "airframe_double_booked",
                        "message": f"Airframe '{airframe_id}' is assigned to multiple concurrent sorties",
                        "refs": [airframe_id]
                    })
                assigned_airframes.add(airframe_id)

            crew_id = a.get("crew_id") or a.get("crewId")
            if crew_id:
                if crew_id in assigned_crews:
                    all_violations.append({
                        "rule": "crew_double_booked",
                        "message": f"Crew '{crew_id}' is assigned to multiple concurrent sorties",
                        "refs": [crew_id]
                    })
                assigned_crews.add(crew_id)

            corridor_id = a.get("corridor_id") or a.get("corridorId")
            slot = a.get("slot", 0)
            if corridor_id and isinstance(slot, int):
                key = (corridor_id, slot)
                if key in corridor_slot_occupancy:
                    all_violations.append({
                        "rule": "corridor_slot_contention",
                        "message": f"Corridor '{corridor_id}' has multiple aircraft assigned at slot {slot}",
                        "refs": [corridor_id]
                    })
                corridor_slot_occupancy.add(key)

        outcome = "verified" if not all_violations else "invalid"
        uncertainty = []
        if any(v["rule"] in ("threat_exceeded", "weather_safety") for v in all_violations):
            uncertainty.append("Environmental or hostile threat factors present")

        return {
            "outcome": outcome,
            "violations": all_violations,
            "uncertainty_flags": uncertainty
        }

