from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.api.phase3_dependencies import phase3_session
from backend.app.core.errors import AppError
from backend.app.db.migrations import assert_database_at_head
from backend.app.services.internal_alpha_quality import (
    InternalAlphaQualityScanner,
    load_internal_alpha_quality_context,
)
from backend.app.services.selection_advice import DEFAULT_ALPHA_ROOT


router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/ready")
def readiness(
    request: Request,
    session: Annotated[Session, Depends(phase3_session)],
) -> dict[str, str | int]:
    settings = request.app.state.settings
    if not settings.model_is_configured:
        raise AppError(
            code="SERVICE_NOT_READY",
            message="服务尚未准备好。",
            status_code=503,
        )
    try:
        assert_database_at_head(session.get_bind())
        context = load_internal_alpha_quality_context(
            root=DEFAULT_ALPHA_ROOT,
            generated_commit=settings.app_version,
        )
        report = InternalAlphaQualityScanner(
            session,
            clock=request.app.state.phase3_clock,
        ).scan(context)
    except Exception as exc:
        raise AppError(
            code="SERVICE_NOT_READY",
            message="服务尚未准备好。",
            status_code=503,
        ) from exc
    if not report.ready_for_internal_mvp:
        raise AppError(
            code="SERVICE_NOT_READY",
            message="服务尚未准备好。",
            status_code=503,
        )
    return {
        "status": "ready",
        "version": settings.app_version,
        "dataset_id": report.dataset_id,
        "program_count": report.program_count,
    }
