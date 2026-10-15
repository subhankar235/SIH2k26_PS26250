"""Tests for PostgreSQL storage layer."""

import pytest
import uuid
from datetime import datetime, timezone
from storage.database import StorageEngine


@pytest.mark.asyncio
async def test_database_init_and_crud():
    # Use the live PostgreSQL container
    db = StorageEngine()
    try:
        await db.init_db()

        # 1. Record an event
        event_id = str(uuid.uuid4())
        event = await db.record_event({
            "event_id": event_id,
            "event_type": "threat.alert",
            "entity_id": "corridor-alpha",
            "source_id": "radar-station-1",
            "sequence": 1,
            "observed_at": datetime.now(timezone.utc),
            "valid_until": datetime.now(timezone.utc),
            "payload": {
                "threatLevel": "high",
                "riskScore": 0.85,
                "threatType": "sam"
            }
        })
        assert event.event_id == event_id
        assert event.event_type == "threat.alert"

        # 2. Save a mission plan
        run_id = str(uuid.uuid4())
        plan = await db.save_plan({
            "run_id": run_id,
            "revision": 1,
            "status": "optimal",
            "objective_score": 92.5,
            "served_priority": 9,
            "threat_risk_score": 0.12,
            "assignments": [
                {
                    "mission_id": "mission-01",
                    "aircraft_id": "airframe-alpha",
                    "corridor_id": "corridor-bravo"
                }
            ],
            "unserved": [],
            "diagnostics": {"solver_time_ms": 14}
        })
        assert plan.run_id == run_id
        assert plan.served_priority == 9

        # 3. Save negotiation transcripts
        transcripts = await db.record_transcripts([
            {
                "plan_id": plan.id,
                "run_id": run_id,
                "revision": 1,
                "round_number": 1,
                "agent_name": "ThreatAgent",
                "message_type": "OBJECTION",
                "content": "SAM radar activity detected in Corridor Alpha; recommend rerouting to Corridor Bravo.",
                "metadata": {"riskScore": 0.85}
            },
            {
                "plan_id": plan.id,
                "run_id": run_id,
                "revision": 1,
                "round_number": 2,
                "agent_name": "Coordinator",
                "message_type": "VERDICT",
                "content": "Unanimous consensus achieved: Flight 101 rerouted via Corridor Bravo.",
                "metadata": {"consensus": True}
            }
        ])
        assert len(transcripts) == 2
        assert transcripts[0].agent_name == "ThreatAgent"

        # 4. Fetch latest plan
        fetched_plan = await db.get_latest_plan(run_id=run_id)
        assert fetched_plan is not None
        assert fetched_plan.id == plan.id

    finally:
        await db.close()

