"""Tests for Google OR-Tools CP-SAT flight optimizer."""

import pytest
from solver.model import Airframe, Crew, Corridor, Mission
from solver.optimizer import AirOperationsOptimizer


@pytest.fixture
def baseline_scenario():
    airframes = [
        Airframe(id="C130-Alpha", capacity_kg=20000, max_range_km=3800),
        Airframe(id="IL76-Bravo", capacity_kg=40000, max_range_km=4200),
        Airframe(id="AN32-Charlie", capacity_kg=6000, max_range_km=2500),
    ]
    crews = [
        Crew(id="Crew-01", qualifications=("transport", "tactical")),
        Crew(id="Crew-02", qualifications=("transport",)),
        Crew(id="Crew-03", qualifications=("transport",)),
    ]
    corridors = [
        Corridor(id="Corr-North-Direct", from_base="Base-A", to_base="Base-B", distance_km=800, flight_time_mins=90, threat_risk=0.1),
        Corridor(id="Corr-North-Detour", from_base="Base-A", to_base="Base-B", distance_km=1100, flight_time_mins=130, threat_risk=0.0),
        Corridor(id="Corr-East", from_base="Base-A", to_base="Base-C", distance_km=600, flight_time_mins=70, threat_risk=0.05),
    ]
    missions = [
        Mission(id="M-Ammo-01", origin_base="Base-A", dest_base="Base-B", payload_kg=15000, priority=9, deadline_slot=4),
        Mission(id="M-Medical-02", origin_base="Base-A", dest_base="Base-B", payload_kg=4000, priority=7, deadline_slot=4),
        Mission(id="M-Rations-03", origin_base="Base-A", dest_base="Base-C", payload_kg=5000, priority=4, deadline_slot=4),
    ]
    return airframes, crews, corridors, missions


def test_baseline_optimal_solution(baseline_scenario):
    airframes, crews, corridors, missions = baseline_scenario
    optimizer = AirOperationsOptimizer()
    result = optimizer.solve(missions, airframes, crews, corridors)

    assert result.status == "optimal"
    assert len(result.assignments) == 3
    assert result.served_priority == 20  # 9 + 7 + 4
    assert result.unserved == []


def test_threat_reroute(baseline_scenario):
    airframes, crews, corridors, missions = baseline_scenario
    # Spike threat on direct corridor beyond mission tolerance
    spiked_corridors = [
        Corridor(id="Corr-North-Direct", from_base="Base-A", to_base="Base-B", distance_km=800, flight_time_mins=90, threat_risk=0.85),
        Corridor(id="Corr-North-Detour", from_base="Base-A", to_base="Base-B", distance_km=1100, flight_time_mins=130, threat_risk=0.0),
        Corridor(id="Corr-East", from_base="Base-A", to_base="Base-C", distance_km=600, flight_time_mins=70, threat_risk=0.05),
    ]
    optimizer = AirOperationsOptimizer()
    result = optimizer.solve(missions, airframes, crews, spiked_corridors)

    assert result.status == "optimal"
    # Missions to Base-B should take the Detour corridor to avoid the 0.85 threat
    assigned_corridors = {a.mission_id: a.corridor_id for a in result.assignments}
    assert assigned_corridors["M-Ammo-01"] == "Corr-North-Detour"
    assert assigned_corridors["M-Medical-02"] == "Corr-North-Detour"


def test_weather_storm_blocks_corridor(baseline_scenario):
    airframes, crews, corridors, missions = baseline_scenario
    # Storm closes both Base-A -> Base-B corridors
    storm_corridors = [
        Corridor(id="Corr-North-Direct", from_base="Base-A", to_base="Base-B", distance_km=800, flight_time_mins=90, threat_risk=0.1, weather_condition="storm"),
        Corridor(id="Corr-North-Detour", from_base="Base-A", to_base="Base-B", distance_km=1100, flight_time_mins=130, threat_risk=0.0, weather_condition="storm"),
        Corridor(id="Corr-East", from_base="Base-A", to_base="Base-C", distance_km=600, flight_time_mins=70, threat_risk=0.05),
    ]
    optimizer = AirOperationsOptimizer()
    result = optimizer.solve(missions, airframes, crews, storm_corridors)

    # Only M-Rations-03 (to Base-C) can be served
    assert result.status == "optimal"
    assert len(result.assignments) == 1
    assert result.assignments[0].mission_id == "M-Rations-03"
    assert len(result.unserved) == 2
    for un in result.unserved:
        assert "corridor_closed_due_to_storm" in un["reasons"]


def test_airframe_maintenance_grounding(baseline_scenario):
    airframes, crews, corridors, missions = baseline_scenario
    # Ground the heavy lifters
    grounded_airframes = [
        Airframe(id="C130-Alpha", capacity_kg=20000, max_range_km=3800, status="maintenance"),
        Airframe(id="IL76-Bravo", capacity_kg=40000, max_range_km=4200, status="maintenance"),
        Airframe(id="AN32-Charlie", capacity_kg=6000, max_range_km=2500, status="available"),
    ]
    optimizer = AirOperationsOptimizer()
    result = optimizer.solve(missions, grounded_airframes, crews, corridors)

    # AN32 only has 6,000kg capacity. Can only serve M-Medical-02 (4000kg) or M-Rations-03 (5000kg).
    # Since M-Medical-02 has priority 7 vs M-Rations-03 priority 4, it should serve Medical!
    assert result.status == "optimal"
    assert len(result.assignments) == 1
    assert result.assignments[0].mission_id == "M-Medical-02"
    assert result.assignments[0].airframe_id == "AN32-Charlie"

