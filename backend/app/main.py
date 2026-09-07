from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.app.api.profile_analysis import router as profile_analysis_router
from backend.app.api.program_catalog import router as program_catalog_router
from backend.app.api.phase3_internal import router as phase3_internal_router
from backend.app.api.phase3_history import router as phase3_history_router
from backend.app.api.phase3_public import router as phase3_public_router
from backend.app.api.phase4_quality import router as phase4_quality_router
from backend.app.api.phase4_review import router as phase4_review_router
from backend.app.api.requirement_evaluations import router as requirement_evaluations_router
from backend.app.api.selection_advice import router as selection_advice_router
from backend.app.api.system import router as system_router
from backend.app.core.config import Settings, get_settings
from backend.app.core.errors import error_payload, install_exception_handlers
from backend.app.core.logging import configure_logging
from backend.app.core.runtime import (
    PROTECTED_POST_PATHS,
    InMemoryRateLimiter,
    request_client_key,
)
from backend.app.rules.evaluator import RequirementEngine
from backend.app.services.profile_analysis import ProfileAnalysisService
from backend.app.services.program_catalog import ProgramCatalogService
from backend.app.services.selection_advice import SelectionAdviceService


STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(
    settings: Settings | None = None,
    profile_analysis_service: ProfileAnalysisService | None = None,
    requirement_engine: RequirementEngine | None = None,
    phase3_session_factory=None,
    phase3_clock: Callable[[], datetime] | None = None,
    phase3_id_factory: Callable[[str], str] | None = None,
    phase4_quality_context_provider=None,
    selection_advice_service: SelectionAdviceService | None = None,
    program_catalog_service: ProgramCatalogService | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    app_settings.assert_runtime_ready()
    logger = configure_logging(
        app_settings.log_level,
        app_settings.log_format,
        app_settings.app_version,
    )

    app = FastAPI(
        title="SkyOffer",
        version="0.5.0",
        description=(
            "真实申请档案 Input → 确定性门槛判断 → DeepSeek 解释 → "
            "可核验选校建议"
        ),
    )
    app.state.settings = app_settings
    app.state.logger = logger
    app.state.profile_analysis_service = profile_analysis_service or ProfileAnalysisService(
        settings=app_settings,
        logger=logger,
    )
    app.state.requirement_engine = requirement_engine or RequirementEngine()
    app.state.selection_advice_service = selection_advice_service or SelectionAdviceService(
        settings=app_settings,
        requirement_engine=app.state.requirement_engine,
        logger=logger,
    )
    app.state.program_catalog_service = program_catalog_service or ProgramCatalogService()
    app.state.phase3_session_factory = phase3_session_factory
    app.state.phase3_db_engine = None
    app.state.phase3_clock = phase3_clock or (lambda: datetime.now(timezone.utc))
    app.state.phase3_id_factory = phase3_id_factory or (
        lambda kind: f"{kind}.{uuid4().hex}"
    )
    app.state.phase4_quality_context_provider = phase4_quality_context_provider
    app.state.rate_limiter = InMemoryRateLimiter(
        requests=app_settings.rate_limit_requests,
        window_seconds=app_settings.rate_limit_window_seconds,
    )

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=app_settings.allowed_host_list,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = f"req_{uuid4().hex[:16]}"
        started = time.monotonic()
        response: JSONResponse | None = None
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                body_too_large = int(content_length) > app_settings.request_max_body_bytes
            except ValueError:
                body_too_large = True
            if body_too_large:
                response = JSONResponse(
                    status_code=413,
                    content=error_payload(
                        code="REQUEST_TOO_LARGE",
                        message="请求内容过大，请精简后重试。",
                        request_id=request.state.request_id,
                    ),
                )

        if (
            response is None
            and app_settings.rate_limit_enabled
            and request.method == "POST"
            and request.url.path in PROTECTED_POST_PATHS
        ):
            client_key = request_client_key(
                request,
                trust_proxy_headers=app_settings.trust_proxy_headers,
            )
            decision = await app.state.rate_limiter.consume(
                f"{client_key}:{request.url.path}"
            )
            if not decision.allowed:
                response = JSONResponse(
                    status_code=429,
                    content=error_payload(
                        code="RATE_LIMITED",
                        message="请求过于频繁，请稍后重试。",
                        request_id=request.state.request_id,
                    ),
                    headers={"Retry-After": str(decision.retry_after_seconds)},
                )
            else:
                request.state.rate_limit_remaining = decision.remaining

        if response is None:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        remaining = getattr(request.state, "rate_limit_remaining", None)
        if remaining is not None:
            response.headers["X-RateLimit-Remaining"] = str(remaining)
        logger.info(
            "request_completed",
            extra={
                "request_id": request.state.request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": max(0, round((time.monotonic() - started) * 1000)),
            },
        )
        return response

    install_exception_handlers(app)
    app.include_router(profile_analysis_router)
    app.include_router(requirement_evaluations_router)
    app.include_router(phase3_internal_router)
    app.include_router(phase3_history_router)
    app.include_router(phase3_public_router)
    app.include_router(phase4_quality_router)
    app.include_router(phase4_review_router)
    app.include_router(selection_advice_router)
    app.include_router(program_catalog_router)
    app.include_router(system_router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def phase_one_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "phase1.html")

    @app.get("/phase2", include_in_schema=False)
    async def phase_two_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "phase2.html")

    @app.get("/phase3", include_in_schema=False)
    async def phase_three_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "phase3.html")

    @app.get("/phase4", include_in_schema=False)
    async def phase_four_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "phase4.html")

    @app.get("/advice", include_in_schema=False)
    async def selection_advice_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "advice.html")

    return app


app = create_app()
