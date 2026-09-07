from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.api.phase3_dependencies import phase3_session
from backend.app.core.errors import AppError
from backend.app.repositories.published_programs import (
    ProgramNotPublishedError,
    PublicationIntegrityError,
    PublishedProgramNotFoundError,
    PublishedProgramReader,
)
from backend.app.schemas.published_programs import PublishedProgramRecord


router = APIRouter(prefix="/api/v1/programs", tags=["phase-three-public"])


@router.get("/{program_id}/published", response_model=PublishedProgramRecord)
def get_published_program(
    program_id: str,
    request: Request,
    session: Annotated[Session, Depends(phase3_session)],
) -> PublishedProgramRecord:
    try:
        return PublishedProgramReader(
            session, clock=request.app.state.phase3_clock
        ).get(program_id)
    except PublishedProgramNotFoundError as exc:
        raise AppError(
            code="PROGRAM_NOT_FOUND",
            message="项目不存在。",
            status_code=404,
        ) from exc
    except ProgramNotPublishedError as exc:
        raise AppError(
            code="PROGRAM_NOT_PUBLISHED",
            message="项目尚无已发布版本。",
            status_code=404,
        ) from exc
    except PublicationIntegrityError as exc:
        raise AppError(
            code="PUBLICATION_INTEGRITY_ERROR",
            message="当前发布数据暂时不可用。",
            status_code=409,
        ) from exc
