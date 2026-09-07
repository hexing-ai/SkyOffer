from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.api.phase3_dependencies import phase3_session
from backend.app.core.errors import AppError
from backend.app.schemas.alpha_quality import AlphaQualityReport
from backend.app.services.alpha_quality_scanner import (
    AlphaQualityScanContext,
    AlphaQualityScanner,
)


router = APIRouter(prefix="/api/v1/internal/alpha-datasets", tags=["phase-four-quality"])


@router.get("/{dataset_id}/quality", response_model=AlphaQualityReport)
def get_alpha_dataset_quality(
    dataset_id: str,
    request: Request,
    session: Annotated[Session, Depends(phase3_session)],
) -> AlphaQualityReport:
    provider = getattr(request.app.state, "phase4_quality_context_provider", None)
    if provider is None:
        raise AppError(
            code="ALPHA_DATASET_NOT_CONFIGURED",
            message="Alpha 数据集质量上下文尚未配置。",
            status_code=404,
        )
    try:
        context = provider(dataset_id)
    except Exception as exc:
        raise AppError(
            code="ALPHA_DATASET_INVALID",
            message="Alpha 数据集质量上下文无法读取。",
            status_code=409,
        ) from exc
    if not isinstance(context, AlphaQualityScanContext):
        raise AppError(
            code="ALPHA_DATASET_INVALID",
            message="Alpha 数据集质量上下文无效。",
            status_code=409,
        )
    if context.manifest.dataset_id != dataset_id:
        raise AppError(
            code="ALPHA_DATASET_NOT_FOUND",
            message="Alpha 数据集不存在。",
            status_code=404,
        )
    return AlphaQualityScanner(
        session,
        clock=request.app.state.phase3_clock,
    ).scan(context)
