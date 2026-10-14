"""Versioned API router registration."""

from fastapi import APIRouter

from backend.app.api.v1.agents import router as agents_router
from backend.app.api.v1.approvals import router as approvals_router
from backend.app.api.v1.audit import router as audit_router
from backend.app.api.v1.benchmarks import router as benchmarks_router
from backend.app.api.v1.evidence import router as evidence_router
from backend.app.api.v1.forecasts import router as forecasts_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.ingestion import router as ingestion_router
from backend.app.api.v1.planning import router as planning_router
from backend.app.api.v1.replanning import router as replanning_router
from backend.app.api.v1.stress import router as stress_router
from backend.app.api.v1.validity import router as validity_router
from backend.app.api.v1.verification import router as verification_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(ingestion_router)
api_router.include_router(evidence_router)
api_router.include_router(validity_router)
api_router.include_router(forecasts_router)
api_router.include_router(planning_router)
api_router.include_router(replanning_router)
api_router.include_router(stress_router)
api_router.include_router(agents_router)
api_router.include_router(verification_router)
api_router.include_router(approvals_router)
api_router.include_router(audit_router)
api_router.include_router(benchmarks_router)
