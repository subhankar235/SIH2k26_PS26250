"""Regression tests covering specific audit findings 1 through 16:
- Finding 1: Verification rejects invalid bounds and non-existent targets
- Finding 2: Final CP-SAT solver enforces crew duty hours strictly
- Finding 4: Gateway entityId translation works in event ingestion
- Finding 5: Aircraft recovery events restore availability
- Finding 6: Weather storm updates all affected corridors
- Finding 7: Arrival deadlines and zero-deadline missions
- Finding 10: Coordinator prevents duplicate resource commitments
"""

import pytest
from httpx import AsyncClient, ASGITransport
from api.server import app
from solver.model import Airframe, Crew, Corridor, Mission
from solver.optimizer import AirOperationsOptimizer
from solver.verifier import IndependentVerifier
from transport.equilibrium import EquilibriumEngine
from negotiation.coordinator import MagiCoordinator


@pytest.mark.asyncio
async def test_finding_1_negative_bounds_and_invalid_targets():
    """Verify that /verification/check and /planning/solve reject negative capacity/horizon."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Negative capacity must fail verification
        res = await client.post("/api/v1/verification/check", json={"capacity": -2, "horizon": -4})
        assert res.status_code == 200
        data = res.json()
        assert data["outcome"] == "invalid"
        assert any(v["rule"] == "invalid_operational_bounds" for v in data["violations"])

        # Non-existent target must fail verification
        res_target = await client.post("/api/v1/verification/check", json={"target_id": "NON_EXISTENT_SCH_999"})
        assert res_target.status_code == 200
        target_data = res_target.json()
        assert target_data["outcome"] == "invalid"
        assert any(v["rule"] == "target_not_found" for v in target_data["violations"])

        # Negative bounds on solve must return invalid schedule
        res_solve = await client.post("/api/v1/planning/solve", json={"capacity": -1, "horizon": -5})
        assert res_solve.status_code == 200
        solve_data = res_solve.json()
        assert solve_data["verification"] == "invalid"


def test_finding_2_solver_enforces_crew_duty_hours():
    """Verify CP-SAT solver rejects crew when remaining duty hours < flight time."""
    optimizer = AirOperationsOptimizer()
    
    airframe = Airframe(id="A-01", capacity_kg=10000, max_range_km=3000)
    # Crew has only 6 minutes (0.1h) remaining
    exhausted_crew = Crew(id="Crew-Tired", qualifications=("transport",), duty_hours_left=0.1)
    corridor = Corridor(id="Corr-01", from_base="Base-A", to_base="Base-B", distance_km=800, flight_time_mins=120)
    mission = Mission(id="M-01", origin_base="Base-A", dest_base="Base-B", payload_kg=5000, priority=9, deadline_slot=4)

    res = optimizer.solve([mission], [airframe], [exhausted_crew], [corridor])
    # The solver MUST NOT assign this crew
    assert len(res.assignments) == 0
    assert "M-01" in [u["mission_id"] for u in res.unserved]


def test_finding_7_zero_deadline_mission_rejected():
    """Verify that a mission with deadline slot 0 is rejected because arrival is > 0."""
    optimizer = AirOperationsOptimizer()
    airframe = Airframe(id="A-01", capacity_kg=10000, max_range_km=3000)
    crew = Crew(id="Crew-01", qualifications=("transport",), duty_hours_left=8.0)
    corridor = Corridor(id="Corr-01", from_base="Base-A", to_base="Base-B", distance_km=800, flight_time_mins=60)
    # Deadline slot 0 means mission must arrive at or before slot 0; flight departs at 0 and arrives at slot 1
    impossible_mission = Mission(id="M-Zero", origin_base="Base-A", dest_base="Base-B", payload_kg=2000, priority=5, deadline_slot=0)

    res = optimizer.solve([impossible_mission], [airframe], [crew], [corridor], slots=[0, 1])
    assert len(res.assignments) == 0


@pytest.mark.asyncio
async def test_finding_4_and_5_gateway_entity_id_and_recovery():
    """Verify event ingestion translates gateway entityId and updates unassigned/recovery assets."""
    engine = EquilibriumEngine()
    airframe = Airframe(id="Aero-101", capacity_kg=15000, max_range_km=3500, status="maintenance")
    crew = Crew(id="Crew-101", duty_hours_left=10.0, status="available")
    corridor = Corridor(id="Corr-101", from_base="Base-A", to_base="Base-B", distance_km=600, flight_time_mins=60)
    mission = Mission(id="M-Pending", origin_base="Base-A", dest_base="Base-B", payload_kg=8000, priority=8)

    engine.initialize_world([airframe], [crew], [corridor], [mission])
    engine.establish_initial_equilibrium()
    # Initially mission is unserved because airframe is in maintenance
    assert len(engine.active_assignments) == 0

    # Ingest recovery event using gateway format (entityId and camelCase)
    gateway_event = {
        "type": "aircraft.status.update",
        "entityId": "Aero-101",
        "payload": {
            "status": "available",
            "capacityKg": 15000
        }
    }
    broken = await engine.ingest_event(gateway_event)
    # State must be updated
    assert engine.airframes["Aero-101"].status == "available"


@pytest.mark.asyncio
async def test_finding_6_weather_updates_all_affected_corridors():
    """Verify that a weather event updates ALL matching corridors to destination."""
    engine = EquilibriumEngine()
    airframe = Airframe(id="A-1", capacity_kg=20000, max_range_km=4000)
    crew = Crew(id="C-1", duty_hours_left=8.0)
    c1 = Corridor(id="Corr-1", from_base="Base-A", to_base="Dest-Leh", distance_km=700, flight_time_mins=60)
    c2 = Corridor(id="Corr-2", from_base="Base-B", to_base="Dest-Leh", distance_km=900, flight_time_mins=80)
    mission = Mission(id="M-1", origin_base="Base-A", dest_base="Dest-Leh", payload_kg=5000)

    engine.initialize_world([airframe], [crew], [c1, c2], [mission])
    engine.establish_initial_equilibrium()

    # Weather storm at Dest-Leh
    weather_event = {
        "event_type": "weather.observation",
        "entityId": "Dest-Leh",
        "payload": {"condition": "storm"}
    }
    await engine.ingest_event(weather_event)

    # BOTH corridors must be marked storm
    assert engine.corridors["Corr-1"].weather_condition == "storm"
    assert engine.corridors["Corr-2"].weather_condition == "storm"


def test_finding_10_negotiation_reserves_resources_across_missions():
    """Verify coordinator does not announce unanimous consensus on the same aircraft for two missions."""
    coordinator = MagiCoordinator()
    airframe = Airframe(id="Single-Airframe", capacity_kg=10000, max_range_km=3000)
    crew = Crew(id="Single-Crew", duty_hours_left=8.0)
    corridor = Corridor(id="Single-Corr", from_base="Base-A", to_base="Base-B", distance_km=600, flight_time_mins=60)

    m1 = Mission(id="M-High", origin_base="Base-A", dest_base="Base-B", payload_kg=4000, priority=9)
    m2 = Mission(id="M-Low", origin_base="Base-A", dest_base="Base-B", payload_kg=4000, priority=6)

    outcome = coordinator.negotiate_and_solve([m1, m2], [airframe], [crew], [corridor])
    candidate_seeds = outcome["candidate_seeds"]
    
    # Must only seed one mission for the single airframe, never both!
    seeded_airframes = [s["airframe_id"] for s in candidate_seeds]
    assert len(seeded_airframes) <= 1


def test_verifier_rejects_missing_crew_and_negative_slot():
    """IndependentVerifier must reject assignments with missing crew or negative departure slots."""
    m = Mission(id="M-01", origin_base="Base-A", dest_base="Base-B", payload_kg=5000, priority=9, deadline_slot=4)
    a = Airframe(id="A-01", capacity_kg=10000, max_range_km=3000)
    c = Crew(id="Crew-01", duty_hours_left=8.0)
    corr = Corridor(id="Corr-01", from_base="Base-A", to_base="Base-B", distance_km=800, flight_time_mins=60)

    # 1. Missing crew
    assignment_no_crew = [{
        "mission_id": "M-01",
        "airframe_id": "A-01",
        "crew_id": None,
        "corridor_id": "Corr-01",
        "slot": 0,
        "estimated_arrival_slot": 1
    }]
    res_no_crew = IndependentVerifier.verify_complete_schedule(assignment_no_crew, [m], [a], [c], [corr])
    assert res_no_crew["outcome"] == "invalid"
    assert any(v["rule"] == "missing_crew" for v in res_no_crew["violations"])

    # 2. Negative departure slot
    assignment_neg_slot = [{
        "mission_id": "M-01",
        "airframe_id": "A-01",
        "crew_id": "Crew-01",
        "corridor_id": "Corr-01",
        "slot": -1,
        "estimated_arrival_slot": 0
    }]
    res_neg_slot = IndependentVerifier.verify_complete_schedule(assignment_neg_slot, [m], [a], [c], [corr])
    assert res_neg_slot["outcome"] == "invalid"
    assert any(v["rule"] == "invalid_departure_slot" for v in res_neg_slot["violations"])


def test_optimizer_and_verifier_130m_consistency():
    """Optimizer and verifier must agree on 130m flight duration (3 slots) and deadline enforcement."""
    optimizer = AirOperationsOptimizer()
    a = Airframe(id="A-01", capacity_kg=10000, max_range_km=3000)
    c = Crew(id="Crew-01", duty_hours_left=8.0)
    # 130 min flight time = (130 + 59) // 60 = 3 slots
    corr_130m = Corridor(id="Corr-Detour", from_base="Base-A", to_base="Base-B", distance_km=900, flight_time_mins=130)

    # Mission with deadline 4: 0 + 3 <= 4 -> Feasible and verifiable
    m_ok = Mission(id="M-Detour-OK", origin_base="Base-A", dest_base="Base-B", payload_kg=5000, priority=9, deadline_slot=4)
    sol_ok = optimizer.solve([m_ok], [a], [c], [corr_130m], slots=[0, 1, 2, 3])
    assert len(sol_ok.assignments) == 1
    asgn_ok = sol_ok.assignments[0]
    assert asgn_ok.estimated_arrival_slot == asgn_ok.slot + 3

    ver_ok = IndependentVerifier.verify_complete_schedule(
        [{
            "mission_id": asgn_ok.mission_id,
            "airframe_id": asgn_ok.airframe_id,
            "crew_id": asgn_ok.crew_id,
            "corridor_id": asgn_ok.corridor_id,
            "slot": asgn_ok.slot,
            "estimated_arrival_slot": asgn_ok.estimated_arrival_slot
        }],
        [m_ok], [a], [c], [corr_130m], horizon=4
    )
    assert ver_ok["outcome"] == "verified"

    # Mission with deadline 2: 0 + 3 > 2 -> Infeasible for optimizer and verifier
    m_tight = Mission(id="M-Detour-Tight", origin_base="Base-A", dest_base="Base-B", payload_kg=5000, priority=9, deadline_slot=2)
    sol_tight = optimizer.solve([m_tight], [a], [c], [corr_130m], slots=[0, 1])
    assert len(sol_tight.assignments) == 0


@pytest.mark.asyncio
async def test_telemetry_duty_hours_zero_preserved():
    """Equilibrium engine must preserve duty_hours_left == 0.0 and not default to 12.0."""
    engine = EquilibriumEngine()
    airframe = Airframe(id="A-1", capacity_kg=10000, max_range_km=3000)
    crew = Crew(id="Crew-Exhausted", duty_hours_left=8.0, status="available")
    corr = Corridor(id="Corr-1", from_base="Base-A", to_base="Base-B", distance_km=600, flight_time_mins=60)
    mission = Mission(id="M-1", origin_base="Base-A", dest_base="Base-B", payload_kg=4000, priority=8)

    engine.initialize_world([airframe], [crew], [corr], [mission])
    engine.establish_initial_equilibrium()
    assert len(engine.active_assignments) == 1

    # Ingest telemetry with duty_hours_left == 0.0
    telemetry_event = {
        "event_type": "crew.telemetry",
        "entityId": "Crew-Exhausted",
        "payload": {
            "duty_hours_left": 0.0,
            "status": "rest_mandated"
        }
    }
    broken = await engine.ingest_event(telemetry_event)
    assert engine.crews["Crew-Exhausted"].duty_hours_left == 0.0
    assert broken is True


@pytest.mark.asyncio
async def test_capacity_drop_below_payload_triggers_replan():
    """Aircraft capacity dropping below assigned mission payload must break equilibrium."""
    engine = EquilibriumEngine()
    airframe = Airframe(id="Aero-Heavy", capacity_kg=12000, max_range_km=3000)
    crew = Crew(id="Crew-1", duty_hours_left=8.0)
    corr = Corridor(id="Corr-1", from_base="Base-A", to_base="Base-B", distance_km=600, flight_time_mins=60)
    mission = Mission(id="M-Cargo", origin_base="Base-A", dest_base="Base-B", payload_kg=10000, priority=9)

    engine.initialize_world([airframe], [crew], [corr], [mission])
    engine.establish_initial_equilibrium()
    assert len(engine.active_assignments) == 1

    # Degrade capacity from 12000kg to 8000kg (payload 10000kg no longer fits)
    degrade_event = {
        "event_type": "aircraft.status.update",
        "entityId": "Aero-Heavy",
        "payload": {
            "status": "degraded",
            "capacityKg": 8000
        }
    }
    broken = await engine.ingest_event(degrade_event)
    assert broken is True


def test_engine_apply_restored_plan():
    """Startup restoration must properly update run_id, revision, and active_assignments."""
    from storage.models import MissionPlan
    engine = EquilibriumEngine()
    
    mock_plan = MissionPlan(
        run_id="RUN-RECOVER-777",
        revision=42,
        status="optimal",
        objective_score=1850.0,
        served_priority=15,
        assignments=[{
            "mission_id": "M-SAVED-1",
            "airframe_id": "A-SAVED",
            "crew_id": "C-SAVED",
            "corridor_id": "CORR-SAVED",
            "slot": 1,
            "estimated_arrival_slot": 3
        }]
    )

    engine.apply_restored_plan(mock_plan)
    assert engine.run_id == "RUN-RECOVER-777"
    assert engine.revision == 42
    assert len(engine.active_assignments) == 1
    assert engine.active_assignments[0]["mission_id"] == "M-SAVED-1"


