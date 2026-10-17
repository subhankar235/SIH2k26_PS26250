"""Google OR-Tools CP-SAT multi-objective optimization engine."""

from typing import List, Dict, Optional, Any, Set
from ortools.sat.python import cp_model
from .model import Airframe, Crew, Corridor, Mission, Assignment, SolverResult


class AirOperationsOptimizer:
    """Exact constraint solver for tactical air operations scheduling."""

    def __init__(self, time_limit_seconds: float = 5.0):
        self.time_limit_seconds = time_limit_seconds

    def solve(
        self,
        missions: List[Mission],
        airframes: List[Airframe],
        crews: List[Crew],
        corridors: List[Corridor],
        slots: List[int] = [0, 1, 2, 3],
        candidate_seed: Optional[List[Dict[str, Any]]] = None,
        prior_assignments: Optional[List[Dict[str, Any]]] = None,
    ) -> SolverResult:
        """Solve the multi-objective flight allocation model."""
        model = cp_model.CpModel()

        # Decision variables: x[(m_id, a_id, c_id, r_id, slot)]
        x = {}
        viable_combinations = []

        prior_set: Set[tuple] = set()
        if prior_assignments:
            for pa in prior_assignments:
                prior_set.add((
                    pa.get("mission_id"),
                    pa.get("airframe_id"),
                    pa.get("crew_id"),
                    pa.get("corridor_id"),
                    pa.get("slot")
                ))

        for m in missions:
            for a in airframes:
                if a.status != "available" or m.payload_kg > a.capacity_kg:
                    continue
                # Temperature control check
                if m.temperature_controlled and getattr(a, "capacity_kg", 0) < 5000:
                    continue
                for c in crews:
                    if c.status != "available" or m.required_qualification not in c.qualifications:
                        continue
                    for r in corridors:
                        if r.from_base != m.origin_base or r.to_base != m.dest_base:
                            continue
                        if r.distance_km > a.max_range_km:
                            continue
                        if r.weather_condition == "storm":
                            continue
                        if r.threat_risk > m.max_threat_tolerance:
                            continue
                        # Duty hours check: crew duty hours left must exceed flight time
                        flight_hours = r.flight_time_mins / 60.0
                        if c.duty_hours_left < flight_hours:
                            continue

                        # Operational time slot (1 hour = 60 mins per slot)
                        flight_slots = max(1, (r.flight_time_mins + 59) // 60)
                        for t in slots:
                            # Arrival slot cannot exceed deadline slot (prevents zero-deadline impossible dispatches)
                            if t + flight_slots > m.deadline_slot:
                                continue

                            var_key = (m.id, a.id, c.id, r.id, t)
                            var = model.new_bool_var(f"x_{m.id}_{a.id}_{c.id}_{r.id}_s{t}")
                            x[var_key] = var
                            viable_combinations.append((m, a, c, r, t, flight_slots, var))

        # Constraint 1: Each mission assigned at most once
        for m in missions:
            m_vars = [var for (m_item, _, _, _, _, _, var) in viable_combinations if m_item.id == m.id]
            if m_vars:
                model.add_at_most_one(m_vars)

        # Constraint 2: Each airframe performs at most one flight across slots
        for a in airframes:
            a_vars = [var for (_, a_item, _, _, _, _, var) in viable_combinations if a_item.id == a.id]
            if a_vars:
                model.add_at_most_one(a_vars)

        # Constraint 3: Each crew performs at most one flight across slots
        for c in crews:
            c_vars = [var for (_, _, c_item, _, _, _, var) in viable_combinations if c_item.id == c.id]
            if c_vars:
                model.add_at_most_one(c_vars)

        # Constraint 4: Corridor capacity per slot (maximum 1 aircraft per slot)
        for r in corridors:
            for t in slots:
                r_vars = [var for (_, _, _, r_item, t_slot, _, var) in viable_combinations if r_item.id == r.id and t_slot == t]
                if r_vars:
                    model.add_at_most_one(r_vars)

        # Apply warm start hint if candidate seed is provided from MAGI agents
        if candidate_seed:
            seed_keys = {
                (s["mission_id"], s["airframe_id"], s.get("crew_id"), s["corridor_id"], s.get("slot", 0))
                for s in candidate_seed
            }
            for (m, a, c, r, t, _, var) in viable_combinations:
                # Match exact mission, airframe, corridor, slot, and compatible crew
                matched = any(
                    (m.id == sk[0] and a.id == sk[1] and r.id == sk[3] and t == sk[4] and (sk[2] is None or c.id == sk[2]))
                    for sk in seed_keys
                )
                if matched:
                    model.add_hint(var, 1)

        # Multi-objective formulation:
        # Maximize: Priority*1000 - Threat*500 - Slot*50 - Churn*200
        objective_terms = []
        for (m, a, c, r, t, _, var) in viable_combinations:
            priority_score = m.priority * 1000
            threat_penalty = int(r.threat_risk * 500)
            delay_penalty = t * 50
            
            # Anti-churn: penalize changing a previously assigned airframe/crew/corridor/slot
            churn_penalty = 0
            if prior_assignments and (m.id, a.id, c.id, r.id, t) not in prior_set:
                churn_penalty = 200

            coeff = priority_score - threat_penalty - delay_penalty - churn_penalty
            objective_terms.append(coeff * var)

        if objective_terms:
            model.maximize(sum(objective_terms))

        # Solve
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.time_limit_seconds
        solver.parameters.num_workers = 2
        status = solver.solve(model)

        status_str = "infeasible"
        if status == cp_model.OPTIMAL:
            status_str = "optimal"
        elif status == cp_model.FEASIBLE:
            status_str = "feasible"
        elif status == cp_model.UNKNOWN:
            status_str = "timeout"

        assignments: List[Assignment] = []
        served_mission_ids: Set[str] = set()
        served_priority = 0
        total_threat_risk = 0.0

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for (m, a, c, r, t, flight_slots, var) in viable_combinations:
                if solver.value(var) == 1:
                    assignments.append(
                        Assignment(
                            mission_id=m.id,
                            airframe_id=a.id,
                            crew_id=c.id,
                            corridor_id=r.id,
                            slot=t,
                            estimated_arrival_slot=t + flight_slots,
                            threat_risk=r.threat_risk,
                        )
                    )
                    served_mission_ids.add(m.id)
                    served_priority += m.priority
                    total_threat_risk += r.threat_risk

        # Collect unserved reasons
        unserved = []
        for m in missions:
            if m.id not in served_mission_ids:
                reasons = []
                # Check why
                matching_airframes = [a for a in airframes if a.status == "available" and a.capacity_kg >= m.payload_kg]
                if not matching_airframes:
                    reasons.append("no_available_airframe_with_capacity")
                matching_corridors = [r for r in corridors if r.from_base == m.origin_base and r.to_base == m.dest_base]
                if not matching_corridors:
                    reasons.append("no_connected_flight_corridor")
                elif all(r.weather_condition == "storm" for r in matching_corridors):
                    reasons.append("corridor_closed_due_to_storm")
                elif all(r.threat_risk > m.max_threat_tolerance for r in matching_corridors):
                    reasons.append("corridor_threat_exceeds_tolerance")
                if not reasons:
                    reasons.append("resource_contention_lower_priority")
                
                unserved.append({
                    "mission_id": m.id,
                    "priority": m.priority,
                    "reasons": reasons
                })

        return SolverResult(
            status=status_str,
            served_priority=served_priority,
            total_threat_risk=round(total_threat_risk, 3),
            assignments=assignments,
            unserved=unserved,
            diagnostics={
                "wall_time_seconds": round(solver.wall_time, 4),
                "num_branches": solver.num_branches,
                "status_code": int(status),
                "status_name": solver.status_name(status),
            }
        )
