"""Dynamic equilibrium engine that monitors state and triggers replanning on disruption."""

import asyncio
import logging
from typing import Dict, Any, List, Optional
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

        # Debounce control
        self._pending_events: List[Dict[str, Any]] = []
        self._replan_task: Optional[asyncio.Task] = None

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
            corridors=list(self.corridors.values()),
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

    async def ingest_event(self, event: Dict[str, Any]) -> bool:
        """Ingest event, check for equilibrium breach, and schedule debounced replan if needed."""
        self._pending_events.append(event)
        broken = self._check_equilibrium_break(event)

        if broken:
            self.is_equilibrium = False
            # Debounce replan trigger
            if self._replan_task and not self._replan_task.done():
                self._replan_task.cancel()
            self._replan_task = asyncio.create_task(self._delayed_replan())

        return broken

    def _check_equilibrium_break(self, event: Dict[str, Any]) -> bool:
        """Evaluate if an event invalidates an active flight assignment."""
        event_type = event.get("event_type") or event.get("type", "")
        entity_id = event.get("entity_id", "")
        data = event.get("payload") or event.get("data", {})

        # 1. Airframe failure on currently assigned aircraft
        if "aircraft" in event_type:
            status = data.get("status", "available")
            if status != "available":
                for a in self.active_assignments:
                    if a["airframe_id"] == entity_id:
                        # Update local state
                        if entity_id in self.airframes:
                            old = self.airframes[entity_id]
                            self.airframes[entity_id] = Airframe(
                                id=old.id,
                                capacity_kg=old.capacity_kg,
                                max_range_km=old.max_range_km,
                                status=status
                            )
                        return True

        # 2. Weather storm on active corridor
        elif "weather" in event_type:
            condition = data.get("condition", "clear")
            if condition == "storm":
                for a in self.active_assignments:
                    corr = self.corridors.get(a["corridor_id"])
                    if corr and (corr.to_base == entity_id or corr.id == entity_id):
                        if corr.id in self.corridors:
                            self.corridors[corr.id] = Corridor(
                                id=corr.id,
                                from_base=corr.from_base,
                                to_base=corr.to_base,
                                distance_km=corr.distance_km,
                                flight_time_mins=corr.flight_time_mins,
                                threat_risk=corr.threat_risk,
                                weather_condition="storm"
                            )
                        return True

        # 3. Threat spike on active corridor
        elif "threat" in event_type:
            risk_score = float(data.get("riskScore", 0.0))
            corridor_id = data.get("corridorId", entity_id)
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

        return False

    async def _delayed_replan(self) -> Dict[str, Any]:
        """Wait for debouncing window, then execute renegotiation and replanning."""
        await asyncio.sleep(self.debounce_seconds)
        return await self.trigger_replan()

    async def trigger_replan(self) -> Dict[str, Any]:
        """Execute peer renegotiation and replanning with anti-churn stability."""
        self.revision += 1
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
                "revision": self.revision,
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
                t["revision"] = self.revision
            await self.storage.record_transcripts(transcripts)
        except Exception as e:
            logger.warning(f"Storage persist warning: {e}")

        return outcome

