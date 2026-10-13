"""HTTP API for the Air Power grid operations dashboard."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.schemas import GridSummary, HealthResponse

app = FastAPI(title="Air Power API", version="0.1.0", description="Grid resilience operations API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Return service liveness status."""
    return HealthResponse(status="ok", service="air-power-api")


@app.get("/api/v1/grid/summary", response_model=GridSummary, tags=["grid"])
def grid_summary() -> GridSummary:
    """Return representative grid KPIs until a live data source is configured."""
    return GridSummary(
        total_assets=128,
        healthy_assets=119,
        active_alerts=3,
        renewable_share=0.42,
        demand_mw=1842.6,
        reserve_margin=0.16,
    )
