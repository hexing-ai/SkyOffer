from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.core.errors import AppError
from backend.app.schemas.program_catalog import (
    ProgramCatalogDetailResponse,
    ProgramCatalogListResponse,
)
from backend.app.services.program_catalog import (
    ProgramCatalogDataError,
    ProgramCatalogNotFoundError,
)


router = APIRouter(prefix="/api/v1/programs", tags=["program-catalog"])


@router.get("", response_model=ProgramCatalogListResponse)
def list_programs(request: Request) -> ProgramCatalogListResponse:
    try:
        return request.app.state.program_catalog_service.list_programs()
    except ProgramCatalogDataError as exc:
        raise AppError(
            code="PROGRAM_CATALOG_UNAVAILABLE",
            message="项目数据库暂时不可用。",
            status_code=503,
        ) from exc


@router.get("/{program_ref}", response_model=ProgramCatalogDetailResponse)
def get_program(program_ref: str, request: Request) -> ProgramCatalogDetailResponse:
    try:
        return request.app.state.program_catalog_service.get_program(program_ref)
    except ProgramCatalogNotFoundError as exc:
        raise AppError(
            code="PROGRAM_NOT_FOUND",
            message="项目不存在。",
            status_code=404,
        ) from exc
    except ProgramCatalogDataError as exc:
        raise AppError(
            code="PROGRAM_CATALOG_UNAVAILABLE",
            message="项目数据库暂时不可用。",
            status_code=503,
        ) from exc
