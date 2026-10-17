"""Tests for MAGI multi-agent negotiation protocol and coordinator."""

import pytest
from solver.model import Airframe, Crew, Corridor, Mission
from negotiation.coordinator import MagiCoordinator


@pytest.fixture
def air_ops_env():
    airframes = [
        Airframe(id="C130-Alpha", capacity_kg=20000, max_range_km=3800),
        Airframe(id="AN32-Bravo", capacity_kg=6000, max_range_km=2500),
    ]
    crews = [
        Crew(id="Crew-Tactical", qualifications=("transport", "tactical")),
        Crew(id="Crew-Standard", qualifications=("transport",)),
    ]
    corridors = [
        Corridor(id="Corr-Alpha-HighThreat", from_base="Base-A", to_base="Base-B", distance_km=800, flight_time_mins=90, threat_risk=0.85),
        Corridor(id="Corr-Beta-SafeDetour", from_base="Base-A", to_base="Base-B", distance_km=1050, flight_time_mins=120, threat_risk=0.15),
    ]
    missions = [
        Mission(
            id="M-Ammo-Critical",
            origin_base="Base-A",
            dest_base="Base-B",
            payload_kg=12000,
            priority=10,
            max_threat_tolerance=0.5
        )
    ]
    return airframes, crews, corridors, missions


def test_magi_negotiation_threat_objection_and_counterbid(air_ops_env):
    airframes, crews, corridors, missions = air_ops_env
    coordinator = MagiCoordinator()

    outcome = coordinator.negotiate_and_solve(missions, airframes, crews, corridors)

    # 1. Verify transcripts contain debate
    transcripts = outcome["transcripts"]
    assert len(transcripts) > 0

    # ThreatAgent should object to Corr-Alpha-HighThreat
    threat_objections = [
        t for t in transcripts
        if t.agent_name in ("THREAT-INTEL-05", "MAGI-Threat") and t.message_type == "OBJECTION"
    ]
    assert len(threat_objections) >= 1
    assert "exceeds mission tolerance" in threat_objections[0].content

    # ThreatAgent should propose counter-bid
    counter_bids = [
        t for t in transcripts
        if t.agent_name in ("THREAT-INTEL-05", "MAGI-Threat") and t.message_type == "COUNTER_BID"
    ]
    assert len(counter_bids) >= 1

    # Consensus must be reached on safe corridor Corr-Beta-SafeDetour
    verdicts = [
        t for t in transcripts
        if t.agent_name == "Coordinator" and "Unanimous agreement" in t.content
    ]
    assert len(verdicts) >= 1

    # Solver result must be optimal and routed via the safe detour
    solver_result = outcome["solver_result"]
    assert solver_result.status == "optimal"
    assert len(solver_result.assignments) == 1
    assignment = solver_result.assignments[0]
    assert assignment.airframe_id == "C130-Alpha"
    assert assignment.corridor_id == "Corr-Beta-SafeDetour"
    assert assignment.threat_risk == 0.15


def test_magi_crew_qualification_objection(air_ops_env):
    airframes, crews, corridors, missions = air_ops_env
    # Mission requires tactical qualification
    special_mission = Mission(
        id="M-Special-Ops",
        origin_base="Base-A",
        dest_base="Base-B",
        payload_kg=3000,
        priority=8,
        required_qualification="tactical"
    )

    coordinator = MagiCoordinator()
    outcome = coordinator.negotiate_and_solve([special_mission], airframes, crews, corridors)

    # CrewAgent should approve Crew-Tactical and reject Crew-Standard
    transcripts = outcome["transcripts"]
    crew_accepts = [
        t for t in transcripts
        if t.agent_name in ("CREW-LOGISTICS-02", "Balthasar-Crew") and t.message_type == "ACCEPT"
    ]
    crew_rejects = [
        t for t in transcripts
        if t.agent_name in ("CREW-LOGISTICS-02", "Balthasar-Crew") and t.message_type == "OBJECTION"
    ]
    assert len(crew_accepts) >= 1
    assert any("certified" in t.content for t in crew_accepts)
    if crew_rejects:
        assert any("lacks 'tactical'" in t.content for t in crew_rejects)

