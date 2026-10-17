"""Specialized MAGI domain agents for Air Operations."""

from typing import Dict, Any, Optional
from solver.model import Mission, Airframe, Crew, Corridor
from models.turnaround import TurnaroundPredictor
from models.weather_trend import WeatherTrendPredictor
from models.threat_scorer import ThreatRiskScorer
from .base import BaseMagiAgent, AgentVote


class FleetAgent(BaseMagiAgent):
    """Evaluates airframe readiness, capacity, range, and turnaround stress."""

    def __init__(self, name: str = "AERO-FLEET-01"):
        super().__init__(name=name, domain="fleet")
        self.turnaround_predictor = TurnaroundPredictor()

    def evaluate_candidate(
        self,
        mission: Mission,
        airframe: Airframe,
        crew: Crew,
        corridor: Corridor,
        slot: int
    ) -> AgentVote:
        if airframe.status != "available":
            return AgentVote(
                agent_name=self.name,
                approved=False,
                confidence=0.99,
                objection_code="AIRFRAME_UNAVAILABLE",
                rationale=f"Airframe {airframe.id} is currently flagged as {airframe.status}."
            )

        if mission.payload_kg > airframe.capacity_kg:
            return AgentVote(
                agent_name=self.name,
                approved=False,
                confidence=1.0,
                objection_code="PAYLOAD_EXCEEDS_CAPACITY",
                rationale=f"Mission payload {mission.payload_kg}kg exceeds {airframe.id} maximum capacity ({airframe.capacity_kg}kg)."
            )

        if corridor.distance_km > airframe.max_range_km:
            return AgentVote(
                agent_name=self.name,
                approved=False,
                confidence=1.0,
                objection_code="RANGE_EXCEEDED",
                rationale=f"Route distance {corridor.distance_km}km exceeds airframe operational range ({airframe.max_range_km}km)."
            )

        # Predict turnaround
        predicted_turnaround = self.turnaround_predictor.predict_turnaround_mins(
            flight_hours=float(self.state.get(f"{airframe.id}_hours", 1200.0)),
            payload_kg=mission.payload_kg,
            capacity_kg=airframe.capacity_kg
        )
        delay_prob = self.turnaround_predictor.predict_delay_probability(predicted_turnaround)

        return AgentVote(
            agent_name=self.name,
            approved=True,
            confidence=round(1.0 - delay_prob, 2),
            rationale=f"Airframe {airframe.id} certified. Expected turnaround {predicted_turnaround}m (delay risk: {int(delay_prob*100)}%)."
        )


class CrewAgent(BaseMagiAgent):
    """Evaluates pilot qualifications, flight hour caps, and duty windows."""

    def __init__(self, name: str = "CREW-LOGISTICS-02"):
        super().__init__(name=name, domain="crew")

    def evaluate_candidate(
        self,
        mission: Mission,
        airframe: Airframe,
        crew: Crew,
        corridor: Corridor,
        slot: int
    ) -> AgentVote:
        if crew.status != "available":
            return AgentVote(
                agent_name=self.name,
                approved=False,
                confidence=0.99,
                objection_code="CREW_UNAVAILABLE",
                rationale=f"Crew {crew.id} is in status '{crew.status}' (mandatory rest cycle)."
            )

        if mission.required_qualification not in crew.qualifications:
            return AgentVote(
                agent_name=self.name,
                approved=False,
                confidence=1.0,
                objection_code="QUALIFICATION_MISMATCH",
                rationale=f"Crew {crew.id} lacks '{mission.required_qualification}' certification."
            )

        # Flight duration check against duty hours
        flight_hours = corridor.flight_time_mins / 60.0
        if flight_hours > crew.duty_hours_left:
            return AgentVote(
                agent_name=self.name,
                approved=False,
                confidence=0.95,
                objection_code="DUTY_LIMIT_EXCEEDED",
                rationale=f"Flight duration ({flight_hours:.1f}h) exceeds crew {crew.id} remaining duty ({crew.duty_hours_left:.1f}h)."
            )

        return AgentVote(
            agent_name=self.name,
            approved=True,
            confidence=0.95,
            rationale=f"Crew {crew.id} certified and well within duty bounds ({crew.duty_hours_left:.1f}h remaining)."
        )


class PayloadAgent(BaseMagiAgent):
    """Evaluates mission urgency, handling requirements, and deadlines."""

    def __init__(self, name: str = "ARMAMENT-ALLOC-03"):
        super().__init__(name=name, domain="payload")

    def evaluate_candidate(
        self,
        mission: Mission,
        airframe: Airframe,
        crew: Crew,
        corridor: Corridor,
        slot: int
    ) -> AgentVote:
        if slot > mission.deadline_slot:
            return AgentVote(
                agent_name=self.name,
                approved=False,
                confidence=1.0,
                objection_code="DEADLINE_BREACHED",
                rationale=f"Scheduled departure slot {slot} breaches mission deadline slot {mission.deadline_slot}."
            )

        urgency_rating = "CRITICAL" if mission.priority >= 8 else "STANDARD"
        return AgentVote(
            agent_name=self.name,
            approved=True,
            confidence=round(min(1.0, 0.6 + 0.04 * mission.priority), 2),
            rationale=f"Priority {mission.priority}/10 [{urgency_rating}] payload accepted for scheduled slot {slot}."
        )


class ThreatAgent(BaseMagiAgent):
    """Evaluates corridor threat umbrella, radar exposure, and suggests detours."""

    def __init__(self, name: str = "THREAT-INTEL-05"):
        super().__init__(name=name, domain="threat")
        self.threat_scorer = ThreatRiskScorer()

    def evaluate_candidate(
        self,
        mission: Mission,
        airframe: Airframe,
        crew: Crew,
        corridor: Corridor,
        slot: int
    ) -> AgentVote:
        threat_risk = corridor.threat_risk

        if threat_risk > mission.max_threat_tolerance:
            return AgentVote(
                agent_name=self.name,
                approved=False,
                confidence=0.98,
                objection_code="THREAT_LEVEL_CRITICAL",
                rationale=f"Corridor {corridor.id} threat risk ({threat_risk:.2f}) exceeds mission tolerance threshold ({mission.max_threat_tolerance:.2f}).",
                suggested_alternative={"avoid_corridor": corridor.id}
            )

        confidence = round(1.0 - threat_risk * 0.5, 2)
        return AgentVote(
            agent_name=self.name,
            approved=True,
            confidence=confidence,
            rationale=f"Corridor {corridor.id} threat environment acceptable (risk: {threat_risk:.2f})."
        )


class WeatherAgent(BaseMagiAgent):
    """Evaluates weather radar, convective activity, and runway minima."""

    def __init__(self, name: str = "MET-ATMOSPHERE-06"):
        super().__init__(name=name, domain="weather")
        self.trend_predictor = WeatherTrendPredictor()

    def evaluate_candidate(
        self,
        mission: Mission,
        airframe: Airframe,
        crew: Crew,
        corridor: Corridor,
        slot: int
    ) -> AgentVote:
        if corridor.weather_condition == "storm":
            return AgentVote(
                agent_name=self.name,
                approved=False,
                confidence=1.0,
                objection_code="CONVECTIVE_STORM_ACTIVITY",
                rationale=f"Corridor {corridor.id} closed due to severe storm cells.",
                suggested_alternative={"avoid_corridor": corridor.id}
            )

        return AgentVote(
            agent_name=self.name,
            approved=True,
            confidence=0.92,
            rationale=f"Corridor {corridor.id} weather condition '{corridor.weather_condition}' is clear for instrument flight."
        )

