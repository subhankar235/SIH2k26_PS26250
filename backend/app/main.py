"""FastAPI application factory and ASGI application."""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from backend.app.api.router import api_router
from backend.app.core.config import Settings, get_settings
from backend.app.core.exceptions import AirPowerError
from backend.app.core.logging import configure_logging, correlation_id_var
from backend.app.schemas import GridSummary, HealthResponse
from backend.app.schemas.common import ErrorResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the configured FastAPI application.

    Args:
        settings: Optional settings object, useful for controlled app construction.

    Returns:
        The configured FastAPI application.
    """
    active_settings = settings or get_settings()
    configure_logging()
    application = FastAPI(
        title="Air Power API",
        version="0.1.0",
        description="Grid resilience operations API",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def set_correlation_id(request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get("X-Request-ID", "").strip() or str(uuid4())
        token = correlation_id_var.set(correlation_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = correlation_id
            return response
        finally:
            correlation_id_var.reset(token)

    @application.exception_handler(AirPowerError)
    async def handle_airpower_error(_request: Request, error: AirPowerError) -> JSONResponse:
        payload = ErrorResponse(
            code=error.code,
            message=error.message,
            details=error.details,
        )
        return JSONResponse(status_code=error.http_status, content=payload.model_dump(mode="json"))

    application.include_router(api_router, prefix="/api/v1")

    # Keep the original public liveness and demo summary routes available.
    @application.get("/health", response_model=HealthResponse, tags=["system"])
    def legacy_health() -> HealthResponse:
        """Return basic service liveness for existing clients."""
        return HealthResponse(status="ok", service="air-power-api")

    @application.get("/api/v1/grid/summary", response_model=GridSummary, tags=["grid"])
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

    return application


app = create_app()
