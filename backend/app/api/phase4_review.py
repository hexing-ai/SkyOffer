from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from backend.app.api.phase3_dependencies import phase3_session
from backend.app.core.errors import AppError
from backend.app.schemas.alpha_review import (
    AlphaReviewProgramDetail,
    AlphaReviewProgramList,
)
from backend.app.services.alpha_quality_scanner import AlphaQualityScanContext
from backend.app.services.alpha_review_service import (
    AlphaReviewDatasetNotFoundError,
    AlphaReviewError,
    AlphaReviewProgramNotFoundError,
    AlphaReviewService,
    AlphaReviewVersionNotFoundError,
)


router = APIRouter(
    prefix="/api/v1/internal/alpha-datasets",
    tags=["phase-four-review"],
)


def _context(request: Request, dataset_id: str) -> AlphaQualityScanContext:
    provider = getattr(request.app.state, "phase4_quality_context_provider", None)
    if provider is None:
        raise AppError(
            code="ALPHA_DATASET_NOT_CONFIGURED",
            message="Alpha 数据集质检上下文尚未配置。",
            status_code=404,
        )
    try:
        context = provider(dataset_id)
    except Exception as exc:
        raise AppError(
            code="ALPHA_DATASET_INVALID",
            message="Alpha 数据集质检上下文无法读取。",
            status_code=409,
        ) from exc
    if not isinstance(context, AlphaQualityScanContext):
        raise AppError(
            code="ALPHA_DATASET_INVALID",
            message="Alpha 数据集质检上下文无效。",
            status_code=409,
        )
    if context.manifest.dataset_id != dataset_id:
        raise AppError(
            code="ALPHA_DATASET_NOT_FOUND",
            message="Alpha 数据集不存在。",
            status_code=404,
        )
    return context


def _translate_review_error(exc: AlphaReviewError) -> AppError:
    if isinstance(exc, AlphaReviewDatasetNotFoundError):
        return AppError(
            code="ALPHA_DATASET_NOT_READY",
            message="Alpha 数据集尚未冻结，不能进入人工质检。",
            status_code=409,
        )
    if isinstance(exc, AlphaReviewProgramNotFoundError):
        return AppError(
            code="ALPHA_PROGRAM_NOT_FOUND",
            message="质检项目不存在或尚未导入。",
            status_code=404,
        )
    if isinstance(exc, AlphaReviewVersionNotFoundError):
        return AppError(
            code="ALPHA_REVIEW_VERSION_NOT_FOUND",
            message="冻结 Pack 对应的候选版本不存在。",
            status_code=409,
        )
    return AppError(
        code="ALPHA_REVIEW_UNAVAILABLE",
        message="该项目当前无法生成安全的质检视图。",
        status_code=409,
    )


@router.get("/{dataset_id}/programs", response_model=AlphaReviewProgramList)
def list_alpha_review_programs(
    dataset_id: str,
    request: Request,
    session: Annotated[Session, Depends(phase3_session)],
    offset: Annotated[int, Query(ge=0, le=30)] = 0,
    limit: Annotated[int, Query(ge=1, le=30)] = 30,
) -> AlphaReviewProgramList:
    try:
        return AlphaReviewService(
            session,
            clock=request.app.state.phase3_clock,
        ).list_programs(
            _context(request, dataset_id),
            offset=offset,
            limit=limit,
        )
    except AlphaReviewError as exc:
        raise _translate_review_error(exc) from exc


@router.get(
    "/{dataset_id}/programs/{pack_ref}",
    response_model=AlphaReviewProgramDetail,
)
def get_alpha_review_program(
    dataset_id: str,
    pack_ref: str,
    request: Request,
    session: Annotated[Session, Depends(phase3_session)],
) -> AlphaReviewProgramDetail:
    try:
        return AlphaReviewService(
            session,
            clock=request.app.state.phase3_clock,
        ).program_detail(
            _context(request, dataset_id),
            pack_ref=pack_ref,
        )
    except AlphaReviewError as exc:
        raise _translate_review_error(exc) from exc
