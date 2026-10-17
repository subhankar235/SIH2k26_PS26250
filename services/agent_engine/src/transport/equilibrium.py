"""Dynamic equilibrium engine that monitors state and triggers replanning on disruption."""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from solver.model import Mission, Airframe, Crew, Corridor, SolverResult
from negotiation.coordinator import MagiCoordinator
from storage.database import StorageEngine

logger = logging.getLogger("EquilibriumEngine")


class EquilibriumEngine:
    """Manages active operational state and renegotiates when equilibrium breaks."""

    def __init__(
        self,
        coordinator: Optional[MagiCoordinator] = None,
        storage: Optional[StorageEngine] = None,
        debounce_seconds: float = 1.0
    ):
        self.coordinator = coordinator or MagiCoordinator()
        self.storage = storage or StorageEngine()
        self.debounce_seconds = debounce_seconds

        # World state
        self.airframes: Dict[str, Airframe] = {}
        self.crews: Dict[str, Crew] = {}
        self.corridors: Dict[str, Corridor] = {}
        self.missions: Dict[str, Mission] = {}

        # Active equilibrium state
        self.active_plan: Optional[SolverResult] = None
        self.active_assignments: List[Dict[str, Any]] = []
        self.run_id: str = "run-001"
        self.revision: int = 0
        self.is_equilibrium: bool = True

        # Debounce control and concurrency
        self._pending_events: List[Dict[str, Any]] = []
        self._replan_task: Optional[asyncio.Task] = None
        self._replan_lock = asyncio.Lock()
        self.ingested_event_ids: Set[str] = set()
        self.entity_sequences: Dict[str, int] = {}
        self.closed_airports: Set[str] = set()

    def initialize_world(
        self,
        airframes: List[Airframe],
        crews: List[Crew],
        corridors: List[Corridor],
        missions: List[Mission],
        run_id: str = "run-001"
    ) -> None:
        """Seed initial baseline state."""
        self.airframes = {a.id: a for a in airframes}
        self.crews = {c.id: c for c in crews}
        self.corridors = {r.id: r for r in corridors}
        self.missions = {m.id: m for m in missions}
        self.run_id = run_id
        self.revision = 0

    def establish_initial_equilibrium(self) -> Dict[str, Any]:
        """Compute the initial baseline optimal plan."""
        outcome = self.coordinator.negotiate_and_solve(
            missions=list(self.missions.values()),
            airframes=list(self.airframes.values()),
            crews=list(self.crews.values()),
            corridors=list(self.corridors.values())
        )
        self.active_plan = outcome["solver_result"]
        self.active_assignments = [
            {
                "mission_id": a.mission_id,
                "airframe_id": a.airframe_id,
                "crew_id": a.crew_id,
                "corridor_id": a.corridor_id,
                "slot": a.slot
            }
            for a in self.active_plan.assignments
        ]
        self.is_equilibrium = True
        return outcome

    def apply_restored_plan(self, plan: Any) -> None:
        """Apply a persisted mission plan restored from database storage upon system startup."""
        self.run_id = getattr(plan, "run_id", self.run_id)
        self.revision = getattr(plan, "revision", self.revision)
        raw_assignments = getattr(plan, "assignments", []) or []

        # Validate that all assignments are structurally complete; do not invent missing IDs!
        valid_assignments = []
        has_invalid = False
        for a in raw_assignments:
            m_id = a.get("mission_id") or a.get("taskId")
            a_id = a.get("airframe_id") or a.get("resourceId")
            c_id = a.get("crew_id")
            r_id = a.get("corridor_id")
            if not m_id or not a_id or not c_id or not r_id:
                has_invalid = True
                continue
            valid_assignments.append({
                "mission_id": m_id,
                "airframe_id": a_id,
                "crew_id": c_id,
                "corridor_id": r_id,
                "slot": a.get("slot", a.get("start", 0)),
            })

        if has_invalid or not valid_assignments:
            self.active_assignments = []
            self.is_equilibrium = False
            return

        self.active_assignments = valid_assignments

        # Auto-register restored resources into engine registries so references resolve
        for a in valid_assignments:
            m_id = a["mission_id"]
            a_id = a["airframe_id"]
            c_id = a["crew_id"]
            r_id = a["corridor_id"]
            if m_id not in self.missions:
                self.missions[m_id] = Mission(id=m_id, origin_base="Base-A", dest_base="Base-B", payload_kg=1000, priority=5, deadline_slot=4)
            if a_id not in self.airframes:
                self.airframes[a_id] = Airframe(id=a_id, capacity_kg=2000, max_range_km=2000)
            if c_id not in self.crews:
                self.crews[c_id] = Crew(id=c_id, duty_hours_left=12.0)
            if r_id not in self.corridors:
                self.corridors[r_id] = Corridor(id=r_id, from_base="Base-A", to_base="Base-B", distance_km=500, flight_time_mins=60)

        from solver.model import SolverResult, Assignment
        srv_val = getattr(plan, "served_priority", None)
        th_val = getattr(plan, "threat_risk_score", getattr(plan, "total_threat_risk", None))

        self.active_plan = SolverResult(
            status=getattr(plan, "status", "optimal") or "optimal",
            served_priority=int(srv_val) if srv_val is not None else 0,
            total_threat_risk=float(th_val) if th_val is not None else 0.0,
            assignments=[
                Assignment(
                    mission_id=a["mission_id"],
                    airframe_id=a["airframe_id"],
                    crew_id=a["crew_id"],
                    corridor_id=a["corridor_id"],
                    slot=a["slot"],
                    estimated_arrival_slot=a.get("estimated_arrival_slot", a["slot"] + 1),
                    threat_risk=float(a.get("threat_risk", 0.0) if a.get("threat_risk") is not None else 0.0)
                )
                for a in valid_assignments
            ],
            unserved=getattr(plan, "unserved", []) or []
        )
        self.is_equilibrium = True

    async def ingest_event(self, event: Dict[str, Any]) -> bool:
        """Ingest event, check for equilibrium breach, and schedule debounced replan if needed."""
        # 1. Structural event validation
        if not isinstance(event, dict):
            return False
        event_type = event.get("event_type") or event.get("type")
        if not isinstance(event_type, str) or not event_type:
            return False
        data = event.get("payload") or event.get("data")
        if data is None and isinstance(event.get("observation"), dict):
            data = event["observation"]
        if data is None or not isinstance(data, dict):
            return False

        # Strict numeric validation (no None, bool, negative, or unparseable values)
        for key in ("dutyHoursLeft", "duty_hours_left", "capacityKg", "capacity_kg", "maxRangeKm", "max_range_km"):
            if key in data:
                val = data[key]
                if val is None or isinstance(val, bool) or not isinstance(val, (int, float)) or val < 0:
                    return False

        for key in ("condition", "weather"):
            if key in data:
                val = data[key]
                if val is not None and not isinstance(val, str):
                    return False

        # Append validly parsed event to pending ledger
        self._pending_events.append(event)
        if len(self._pending_events) > 100:
            self._pending_events = self._pending_events[-50:]

        # 2. Idempotency / replay protection
        event_id = event.get("eventId") or event.get("event_id")
        if event_id and event_id in self.ingested_event_ids:
            return False

        # 3. Expiration check
        from datetime import datetime, timezone
        vu = event.get("validUntil") or event.get("valid_until")
        if vu:
            try:
                vu_dt = datetime.fromisoformat(vu.replace("Z", "+00:00"))
                if vu_dt < datetime.now(timezone.utc):
                    return False
            except Exception:
                pass

        # 4. Stale sequence check
        entity_id = event.get("entityId") or event.get("entity_id", "")
        seq = event.get("sequence")
        if seq is not None and isinstance(seq, int) and entity_id:
            last_seq = self.entity_sequences.get(entity_id)
            if last_seq is not None and seq <= last_seq:
                return False
            self.entity_sequences[entity_id] = seq

        broken = self._check_equilibrium_break(event)

        if event_id:
            self.ingested_event_ids.add(event_id)

        if broken:
            self.is_equilibrium = False
            # Debounce replan trigger
            if self._replan_task and not self._replan_task.done():
                self._replan_task.cancel()
            self._replan_task = asyncio.create_task(self._delayed_replan())

        return broken

    def _check_equilibrium_break(self, event: Dict[str, Any]) -> bool:
        """Evaluate if an event invalidates an active flight assignment or opens recovery capacity."""
        event_type = event.get("event_type") or event.get("type", "")
        entity_id = event.get("entityId") or event.get("entity_id", "")
        data = event.get("payload") or event.get("data", {})
        if not data and isinstance(event.get("observation"), dict):
            data = event["observation"]

        # 1. Airframe event
        if "aircraft" in event_type or "airframe" in event_type:
            status = data.get("status", "available")
            new_capacity = None
            if "capacity_kg" in data or "capacityKg" in data:
                raw_cap = data.get("capacity_kg") if "capacity_kg" in data else data.get("capacityKg")
                new_capacity = float(raw_cap)

            new_range = None
            if "max_range_km" in data or "maxRangeKm" in data:
                raw_range = data.get("max_range_km") if "max_range_km" in data else data.get("maxRangeKm")
                new_range = float(raw_range)

            if entity_id in self.airframes:
                old = self.airframes[entity_id]
                cap = new_capacity if new_capacity is not None else old.capacity_kg
                range_val = new_range if new_range is not None else old.max_range_km
                self.airframes[entity_id] = Airframe(
                    id=old.id,
                    capacity_kg=cap,
                    max_range_km=range_val,
                    turnaround_mins=old.turnaround_mins,
                    status=status
                )
            
            # Check if assigned aircraft failed or capacity/range dropped below requirements
            for a in self.active_assignments:
                if a.get("airframe_id") == entity_id:
                    if status != "available":
                        return True
                    if new_capacity is not None:
                        m_id = a.get("mission_id")
                        mission = self.missions.get(m_id)
                        if mission and mission.payload_kg > new_capacity:
                            return True
                    if new_range is not None:
                        r_id = a.get("corridor_id")
                        corridor = self.corridors.get(r_id)
                        if corridor and new_range < corridor.distance_km:
                            return True
            
            # Check if recovered aircraft can serve an unserved mission
            if status == "available" and (not self.active_assignments or (self.active_plan and getattr(self.active_plan, "unserved", None))):
                return True

        # 2. Crew event
        elif "crew" in event_type or "pilot" in event_type:
            status = data.get("status", "available")
            duty_val = data.get("duty_hours_left") if "duty_hours_left" in data else data.get("dutyHoursLeft")
            duty_left = float(duty_val) if duty_val is not None else 12.0

            if entity_id in self.crews:
                old_crew = self.crews[entity_id]
                quals = tuple(data["qualifications"]) if "qualifications" in data else old_crew.qualifications
                self.crews[entity_id] = Crew(
                    id=old_crew.id,
                    qualifications=quals,
                    duty_hours_left=duty_left,
                    status=status
                )
            
            # Check if assigned crew failed, duty hours dropped, or qualification was removed
            for a in self.active_assignments:
                if a.get("crew_id") == entity_id:
                    if status != "available":
                        return True
                    r_id = a.get("corridor_id")
                    corridor = self.corridors.get(r_id)
                    flight_hours = (corridor.flight_time_mins / 60.0) if corridor else 1.0
                    if duty_left < flight_hours:
                        return True
                    m_id = a.get("mission_id")
                    mission = self.missions.get(m_id)
                    if mission and mission.required_qualification not in self.crews[entity_id].qualifications:
                        return True

        # 3. Weather event - updates ALL matching corridors (both destination and departure)
        elif "weather" in event_type or "storm" in event_type:
            condition = data.get("condition") or data.get("weather") or "clear"
            affected_active = False

            for corr_id, corr in list(self.corridors.items()):
                if corr.to_base == entity_id or corr.from_base == entity_id or corr.id == entity_id:
                    self.corridors[corr_id] = Corridor(
                        id=corr.id,
                        from_base=corr.from_base,
                        to_base=corr.to_base,
                        distance_km=corr.distance_km,
                        flight_time_mins=corr.flight_time_mins,
                        threat_risk=corr.threat_risk,
                        weather_condition=condition
                    )
                    if condition == "storm":
                        for a in self.active_assignments:
                            if a["corridor_id"] == corr_id:
                                affected_active = True

            if affected_active:
                return True
            
            # Recovery: if weather cleared, check if unserved sorties can now fly
            if condition != "storm" and (not self.active_assignments or (self.active_plan and getattr(self.active_plan, "unserved", None))):
                return True

        # 4. Threat spike on corridor
        elif "threat" in event_type or "radar" in event_type:
            risk_score = float(data.get("riskScore") or data.get("risk_score") or data.get("risk") or 0.0)
            corridor_id = data.get("corridorId") or data.get("corridor_id") or entity_id
            if corridor_id in self.corridors:
                old_corr = self.corridors[corridor_id]
                self.corridors[corridor_id] = Corridor(
                    id=old_corr.id,
                    from_base=old_corr.from_base,
                    to_base=old_corr.to_base,
                    distance_km=old_corr.distance_km,
                    flight_time_mins=old_corr.flight_time_mins,
                    threat_risk=risk_score,
                    weather_condition=old_corr.weather_condition
                )
                for a in self.active_assignments:
                    if a["corridor_id"] == corridor_id:
                        mission = self.missions.get(a["mission_id"])
                        if mission and risk_score > mission.max_threat_tolerance:
                            return True

        # 5. Airport / Base closure
        elif "airport" in event_type or "base" in event_type:
            status = data.get("status", "closed")
            if status not in ("open", "available"):
                self.closed_airports.add(entity_id)
                # Mark all corridors leading to/from closed airport as storm / closed
                for corr_id, corr in list(self.corridors.items()):
                    if corr.to_base == entity_id or corr.from_base == entity_id:
                        self.corridors[corr_id] = Corridor(
                            id=corr.id,
                            from_base=corr.from_base,
                            to_base=corr.to_base,
                            distance_km=corr.distance_km,
                            flight_time_mins=corr.flight_time_mins,
                            threat_risk=corr.threat_risk,
                            weather_condition="storm"
                        )
                for a in self.active_assignments:
                    m = self.missions.get(a.get("mission_id"))
                    if m and (m.origin_base == entity_id or m.dest_base == entity_id):
                        return True
                    r = self.corridors.get(a.get("corridor_id"))
                    if r and (r.from_base == entity_id or r.to_base == entity_id):
                        return True
            else:
                self.closed_airports.discard(entity_id)

        # 6. Cargo / Mission mass update
        elif "cargo" in event_type or "payload" in event_type or "mission" in event_type:
            raw_mass = data.get("mass_kg") if "mass_kg" in data else (data.get("massKg") or data.get("payload_kg") or data.get("payloadKg"))
            if raw_mass is not None and entity_id in self.missions:
                new_mass = float(raw_mass)
                old_m = self.missions[entity_id]
                self.missions[entity_id] = Mission(
                    id=old_m.id,
                    origin_base=old_m.origin_base,
                    dest_base=old_m.dest_base,
                    payload_kg=new_mass,
                    priority=old_m.priority,
                    deadline_slot=old_m.deadline_slot,
                    required_qualification=old_m.required_qualification,
                    max_threat_tolerance=old_m.max_threat_tolerance,
                    temperature_controlled=old_m.temperature_controlled
                )
                for a in self.active_assignments:
                    if a.get("mission_id") == entity_id:
                        airframe = self.airframes.get(a.get("airframe_id"))
                        if airframe and new_mass > airframe.capacity_kg:
                            return True

        return False

    async def _delayed_replan(self) -> Dict[str, Any]:
        """Wait for debouncing window, then execute renegotiation and replanning."""
        await asyncio.sleep(self.debounce_seconds)
        return await self.trigger_replan()

    async def trigger_replan(self) -> Dict[str, Any]:
        """Execute peer renegotiation and replanning with anti-churn stability."""
        if self._replan_task and not self._replan_task.done():
            self._replan_task.cancel()

        async with self._replan_lock:
            self.revision += 1
            replan_rev = self.revision
            outcome = self.coordinator.negotiate_and_solve(
                missions=list(self.missions.values()),
                airframes=list(self.airframes.values()),
                crews=list(self.crews.values()),
                corridors=list(self.corridors.values()),
                prior_assignments=self.active_assignments,
            )

            self.active_plan = outcome["solver_result"]
            self.active_assignments = [
                {
                    "mission_id": a.mission_id,
                    "airframe_id": a.airframe_id,
                    "crew_id": a.crew_id,
                    "corridor_id": a.corridor_id,
                    "slot": a.slot
                }
                for a in self.active_plan.assignments
            ]
            self.is_equilibrium = True

            # Persist to database if storage initialized
            try:
                plan_record = await self.storage.save_plan({
                    "run_id": self.run_id,
                    "revision": replan_rev,
                    "status": self.active_plan.status,
                    "objective_score": float(self.active_plan.served_priority * 10),
                    "served_priority": self.active_plan.served_priority,
                    "threat_risk_score": self.active_plan.total_threat_risk,
                    "assignments": self.active_assignments,
                    "unserved": self.active_plan.unserved,
                    "diagnostics": self.active_plan.diagnostics
                })

                transcripts = [t.to_dict() for t in outcome["transcripts"]]
                for t in transcripts:
                    t["plan_id"] = plan_record.id
                    t["run_id"] = self.run_id
                    t["revision"] = replan_rev
                await self.storage.record_transcripts(transcripts)
            except Exception as e:
                self.is_equilibrium = False
                logger.warning(f"Storage persist warning: {e}")
                raise

            # Automatic engine broadcast
            try:
                from api.websocket import stream_manager
                await stream_manager.broadcast({
                    "type": "REPLAN_EVENT",
                    "revision": replan_rev,
                    "status": self.active_plan.status,
                    "served_priority": self.active_plan.served_priority,
                    "assignments_count": len(self.active_assignments),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            except Exception as ex:
                logger.debug(f"Stream broadcast note: {ex}")

            return outcome

