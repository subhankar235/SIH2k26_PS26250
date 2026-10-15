"""REST and WebSocket route definitions for the Agent Engine."""

from typing import Dict, Any, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from .websocket import stream_manager
from transport.equilibrium import EquilibriumEngine

router = APIRouter()
_engine_instance: EquilibriumEngine = None


def set_engine(engine: EquilibriumEngine) -> None:
    global _engine_instance
    _engine_instance = engine


def get_engine() -> EquilibriumEngine:
    if not _engine_instance:
        raise HTTPException(status_code=503, detail="Equilibrium engine not initialized")
    return _engine_instance


@router.get("/health")
@router.get("/health/live")
@router.get("/api/v1/health")
async def health_live():
    return {"status": "ok", "service": "agent_engine"}


@router.get("/health/ready")
async def health_ready():
    engine = get_engine()
    return {"status": "ready", "is_equilibrium": engine.is_equilibrium, "revision": engine.revision}


@router.get("/api/v1/status")
async def get_system_status() -> Dict[str, Any]:
    engine = get_engine()
    return {
        "run_id": engine.run_id,
        "revision": engine.revision,
        "is_equilibrium": engine.is_equilibrium,
        "airframes_count": len(engine.airframes),
        "crews_count": len(engine.crews),
        "corridors_count": len(engine.corridors),
        "missions_count": len(engine.missions),
        "active_flights_count": len(engine.active_assignments),
    }


@router.get("/api/v1/plans/active")
async def get_active_plan() -> Dict[str, Any]:
    engine = get_engine()
    if not engine.active_plan:
        return {"status": "no_plan", "assignments": [], "unserved": []}

    return {
        "status": engine.active_plan.status,
        "revision": engine.revision,
        "served_priority": engine.active_plan.served_priority,
        "total_threat_risk": engine.active_plan.total_threat_risk,
        "assignments": [
            {
                "mission_id": a.mission_id,
                "airframe_id": a.airframe_id,
                "crew_id": a.crew_id,
                "corridor_id": a.corridor_id,
                "slot": a.slot,
                "threat_risk": a.threat_risk,
            }
            for a in engine.active_plan.assignments
        ],
        "unserved": engine.active_plan.unserved,
        "diagnostics": engine.active_plan.diagnostics,
    }


@router.post("/api/v1/replan")
async def trigger_manual_replan() -> Dict[str, Any]:
    engine = get_engine()
    outcome = await engine.trigger_replan()

    # Broadcast to live dashboard
    await stream_manager.broadcast({
        "type": "REPLAN_EVENT",
        "revision": engine.revision,
        "served_priority": engine.active_plan.served_priority,
        "assignments_count": len(engine.active_plan.assignments),
    })

    return {
        "status": "replan_complete",
        "revision": engine.revision,
        "served_priority": engine.active_plan.served_priority,
        "assignments": engine.active_assignments,
    }


@router.websocket("/ws/magi/stream")
async def websocket_magi_stream(websocket: WebSocket):
    await stream_manager.connect(websocket)
    try:
        while True:
            # Keep-alive loop receiving client pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        stream_manager.disconnect(websocket)

