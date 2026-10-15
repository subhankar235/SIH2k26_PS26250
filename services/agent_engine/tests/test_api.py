"""Tests for Agent Engine FastAPI endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport
from api.server import app


@pytest.mark.asyncio
async def test_api_health_and_plans():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Health check
        res_live = await client.get("/health/live")
        assert res_live.status_code == 200
        assert res_live.json() == {"status": "ok"}

        # 2. System status
        res_status = await client.get("/api/v1/status")
        assert res_status.status_code == 200
        status_data = res_status.json()
        assert status_data["is_equilibrium"] is True
        assert status_data["missions_count"] == 3
        assert status_data["active_flights_count"] == 3

        # 3. Active plan
        res_plan = await client.get("/api/v1/plans/active")
        assert res_plan.status_code == 200
        plan_data = res_plan.json()
        assert plan_data["status"] == "optimal"
        assert plan_data["served_priority"] == 20
        assert len(plan_data["assignments"]) == 3

        # 4. Manual replan trigger
        res_replan = await client.post("/api/v1/replan")
        assert res_replan.status_code == 200
        replan_data = res_replan.json()
        assert replan_data["status"] == "replan_complete"
        assert replan_data["revision"] == 1

