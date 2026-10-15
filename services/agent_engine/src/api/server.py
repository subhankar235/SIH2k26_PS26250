"""FastAPI application factory for the Agent Engine."""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import router, set_engine
from transport.equilibrium import EquilibriumEngine
from storage.database import StorageEngine
from solver.model import Airframe, Crew, Corridor, Mission


def create_demo_world() -> tuple:
    """Create default tactical air operations baseline assets."""
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
        Mission(id="M-Ammo-01", origin_base="Base-A", dest_base="Base-B", payload_kg=15000, priority=9, deadline_slot=2),
        Mission(id="M-Medical-02", origin_base="Base-A", dest_base="Base-B", payload_kg=4000, priority=7, deadline_slot=2),
        Mission(id="M-Rations-03", origin_base="Base-A", dest_base="Base-C", payload_kg=5000, priority=4, deadline_slot=3),
    ]
    return airframes, crews, corridors, missions


def init_default_engine() -> EquilibriumEngine:
    storage = StorageEngine()
    engine = EquilibriumEngine(storage=storage)
    airframes, crews, corridors, missions = create_demo_world()
    engine.initialize_world(airframes, crews, corridors, missions)
    engine.establish_initial_equilibrium()
    set_engine(engine)
    return engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = init_default_engine()
    try:
        await engine.storage.init_db()
    except Exception:
        pass

    yield

    try:
        await engine.storage.close()
    except Exception:
        pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="MAGI Air Operations & Resource Optimisation Engine",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    # Ensure engine is seeded immediately
    init_default_engine()
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("AGENT_ENGINE_PORT", 8000))
    uvicorn.run("api.server:app", host="127.0.0.1", port=port, reload=False)

