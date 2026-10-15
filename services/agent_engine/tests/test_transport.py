"""Tests for dynamic equilibrium engine and replanning triggers."""

import pytest
import asyncio
from solver.model import Airframe, Crew, Corridor, Mission
from transport.equilibrium import EquilibriumEngine


@pytest.fixture
def equilibrium_env():
    airframes = [
        Airframe(id="C130-Alpha", capacity_kg=20000, max_range_km=3800),
        Airframe(id="AN32-Bravo", capacity_kg=6000, max_range_km=2500),
    ]
    crews = [
        Crew(id="Crew-01", qualifications=("transport",)),
        Crew(id="Crew-02", qualifications=("transport",)),
    ]
    corridors = [
        Corridor(id="Corr-Direct", from_base="Base-A", to_base="Base-B", distance_km=800, flight_time_mins=90, threat_risk=0.1),
        Corridor(id="Corr-Detour", from_base="Base-A", to_base="Base-B", distance_km=1100, flight_time_mins=130, threat_risk=0.05),
    ]
    missions = [
        Mission(id="M-Ammo", origin_base="Base-A", dest_base="Base-B", payload_kg=12000, priority=9, max_threat_tolerance=0.5),
        Mission(id="M-Food", origin_base="Base-A", dest_base="Base-B", payload_kg=4000, priority=5, max_threat_tolerance=0.5),
    ]
    engine = EquilibriumEngine(debounce_seconds=0.1)
    engine.initialize_world(airframes, crews, corridors, missions)
    engine.establish_initial_equilibrium()
    return engine


@pytest.mark.asyncio
async def test_equilibrium_initial_state(equilibrium_env):
    engine = equilibrium_env
    assert engine.is_equilibrium is True
    assert engine.revision == 0
    assert len(engine.active_assignments) == 2


@pytest.mark.asyncio
async def test_benign_event_does_not_break_equilibrium(equilibrium_env):
    engine = equilibrium_env
    # Weather clear event
    broken = await engine.ingest_event({
        "type": "weather.observation",
        "entity_id": "Base-A",
        "data": {"condition": "clear", "windSpeedMps": 5.0}
    })
    assert broken is False
    assert engine.is_equilibrium is True
    assert engine.revision == 0


@pytest.mark.asyncio
async def test_aircraft_fault_breaks_equilibrium_and_replans(equilibrium_env):
    engine = equilibrium_env
    initial_heavy_flight = [a for a in engine.active_assignments if a["mission_id"] == "M-Ammo"][0]
    assigned_airframe = initial_heavy_flight["airframe_id"]

    # Ground the assigned heavy airframe
    broken = await engine.ingest_event({
        "type": "aircraft.status",
        "entity_id": assigned_airframe,
        "data": {"status": "maintenance"}
    })
    assert broken is True
    assert engine.is_equilibrium is False

    # Wait for debounced replanning task to execute
    await asyncio.sleep(0.2)

    assert engine.is_equilibrium is True
    assert engine.revision == 1
    # Heavy mission M-Ammo (12000kg) can no longer fly because AN32 only holds 6000kg!
    # So M-Food (4000kg) will be served by AN32, and M-Ammo is unserved
    new_assignments = {a["mission_id"]: a["airframe_id"] for a in engine.active_assignments}
    assert "M-Food" in new_assignments
    assert new_assignments["M-Food"] == "AN32-Bravo"


@pytest.mark.asyncio
async def test_threat_spike_triggers_corridor_reroute(equilibrium_env):
    engine = equilibrium_env
    # Threat spike on Corr-Direct to 0.85 (exceeds mission tolerance 0.5)
    broken = await engine.ingest_event({
        "type": "threat.alert",
        "entity_id": "Corr-Direct",
        "data": {
            "corridorId": "Corr-Direct",
            "threatLevel": "high",
            "riskScore": 0.85
        }
    })
    assert broken is True

    # Wait for debounced replanning
    await asyncio.sleep(0.2)

    assert engine.is_equilibrium is True
    assert engine.revision == 1
    # Both missions should now be routed via Corr-Detour
    for a in engine.active_assignments:
        assert a["corridor_id"] == "Corr-Detour"

