"""MAGI Multi-Agent Coordinator and Consensus Engine."""

from typing import List, Dict, Any, Optional
from solver.model import Mission, Airframe, Crew, Corridor, SolverResult
from solver.optimizer import AirOperationsOptimizer
from agents.specialists import (
    FleetAgent,
    CrewAgent,
    PayloadAgent,
    ThreatAgent,
    WeatherAgent,
)
from .protocol import NegotiationMessage


class MagiCoordinator:
    """Orchestrates multi-round MAGI peer deliberation and feeds warm starts into OR-Tools."""

    def __init__(
        self,
        optimizer: Optional[AirOperationsOptimizer] = None,
        max_rounds: int = 4
    ):
        self.optimizer = optimizer or AirOperationsOptimizer()
        self.max_rounds = max_rounds
        self.agents = [
            FleetAgent(),
            CrewAgent(),
            PayloadAgent(),
            ThreatAgent(),
            WeatherAgent(),
        ]

    def update_agent_telemetry(self, domain: str, telemetry: Dict[str, Any]) -> None:
        """Propagate live domain telemetry to the relevant specialist."""
        for agent in self.agents:
            if agent.domain == domain:
                agent.update_telemetry(telemetry)

    def negotiate_and_solve(
        self,
        missions: List[Mission],
        airframes: List[Airframe],
        crews: List[Crew],
        corridors: List[Corridor],
        slots: List[int] = [0, 1, 2, 3],
        prior_assignments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Execute the MAGI consensus process followed by CP-SAT optimization."""
        transcripts: List[NegotiationMessage] = []
        candidate_seeds: List[Dict[str, Any]] = []

        # Sort missions by priority (highest priority negotiated first)
        sorted_missions = sorted(missions, key=lambda m: m.priority, reverse=True)

        for mission in sorted_missions:
            # Find matching corridors for this mission's trajectory
            connected_corridors = [
                r for r in corridors if r.from_base == mission.origin_base and r.to_base == mission.dest_base
            ]
            if not connected_corridors:
                transcripts.append(
                    NegotiationMessage(
                        agent_name="Coordinator",
                        message_type="OBJECTION",
                        mission_id=mission.id,
                        round_number=1,
                        content=f"No connected flight corridors found between {mission.origin_base} and {mission.dest_base}.",
                        metadata={"status": "infeasible"}
                    )
                )
                continue

            # Candidate exploration
            consensus_reached = False
            for round_num in range(1, self.max_rounds + 1):
                # Propose candidate configuration
                for airframe in airframes:
                    if consensus_reached:
                        break
                    for crew in crews:
                        if consensus_reached:
                            break
                        for corridor in connected_corridors:
                            if consensus_reached:
                                break
                            slot = min(mission.deadline_slot, slots[0])

                            transcripts.append(
                                NegotiationMessage(
                                    agent_name="Coordinator",
                                    message_type="PROPOSAL",
                                    mission_id=mission.id,
                                    round_number=round_num,
                                    content=f"Proposing Mission {mission.id} -> Airframe {airframe.id}, Crew {crew.id}, via {corridor.id} at slot {slot}.",
                                    metadata={
                                        "airframe_id": airframe.id,
                                        "crew_id": crew.id,
                                        "corridor_id": corridor.id,
                                        "slot": slot
                                    }
                                )
                            )

                            # Poll all 5 MAGI specialist agents
                            votes = []
                            objections = []
                            for agent in self.agents:
                                vote = agent.evaluate_candidate(mission, airframe, crew, corridor, slot)
                                votes.append(vote)
                                transcripts.append(
                                    NegotiationMessage(
                                        agent_name=agent.name,
                                        message_type="ACCEPT" if vote.approved else "OBJECTION",
                                        mission_id=mission.id,
                                        round_number=round_num,
                                        content=vote.rationale,
                                        metadata={
                                            "approved": vote.approved,
                                            "confidence": vote.confidence,
                                            "objection_code": vote.objection_code
                                        }
                                    )
                                )
                                if not vote.approved:
                                    objections.append((agent, vote))

                            # Check for unanimous consensus
                            if not objections:
                                consensus_reached = True
                                transcripts.append(
                                    NegotiationMessage(
                                        agent_name="Coordinator",
                                        message_type="VERDICT",
                                        mission_id=mission.id,
                                        round_number=round_num,
                                        content=f"Unanimous agreement across all 5 MAGI specialists for {mission.id}.",
                                        metadata={"consensus": True, "airframe_id": airframe.id}
                                    )
                                )
                                candidate_seeds.append({
                                    "mission_id": mission.id,
                                    "airframe_id": airframe.id,
                                    "crew_id": crew.id,
                                    "corridor_id": corridor.id,
                                    "slot": slot
                                })
                            else:
                                # Counter-bidding handling
                                for agent, obj_vote in objections:
                                    if obj_vote.suggested_alternative:
                                        transcripts.append(
                                            NegotiationMessage(
                                                agent_name=agent.name,
                                                message_type="COUNTER_BID",
                                                mission_id=mission.id,
                                                round_number=round_num,
                                                content=f"{agent.name} proposes counter-bid: avoid {obj_vote.suggested_alternative.get('avoid_corridor')} and seek alternate route.",
                                                metadata=obj_vote.suggested_alternative
                                            )
                                        )

        # Feed the negotiated seeds as warm starts to OR-Tools CP-SAT
        solver_result = self.optimizer.solve(
            missions=missions,
            airframes=airframes,
            crews=crews,
            corridors=corridors,
            slots=slots,
            candidate_seed=candidate_seeds,
            prior_assignments=prior_assignments,
        )

        transcripts.append(
            NegotiationMessage(
                agent_name="Coordinator",
                message_type="VERDICT",
                mission_id="GLOBAL",
                round_number=self.max_rounds,
                content=f"Mathematical optimization finalized: {solver_result.status.upper()} (Served Priority: {solver_result.served_priority}, Total Threat Risk: {solver_result.total_threat_risk:.2f}).",
                metadata={
                    "solver_status": solver_result.status,
                    "served_priority": solver_result.served_priority,
                    "num_assignments": len(solver_result.assignments)
                }
            )
        )

        return {
            "solver_result": solver_result,
            "transcripts": transcripts,
            "candidate_seeds": candidate_seeds,
        }

