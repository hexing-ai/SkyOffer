from __future__ import annotations

from typing import Annotated, Callable, TypeVar

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.api.phase3_dependencies import phase3_session
from backend.app.core.errors import AppError
from backend.app.repositories.version_history import (
    VersionHistoryIntegrityError,
    VersionHistoryProgramNotFoundError,
    VersionHistoryRepository,
    VersionHistoryVersionNotFoundError,
)
from backend.app.schemas.version_history import (
    AuditTimelineRecord,
    InternalVersionDiff,
    InternalVersionList,
    InternalVersionRecord,
)


router = APIRouter(prefix="/api/v1/internal", tags=["phase-three-history"])
ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


def _read(handler: Callable[[], ResponseModel]) -> ResponseModel:
    try:
        return handler()
    except VersionHistoryProgramNotFoundError as exc:
        raise AppError(
            code="PROGRAM_NOT_FOUND", message="项目不存在。", status_code=404
        ) from exc
    except VersionHistoryVersionNotFoundError as exc:
        raise AppError(
            code="VERSION_NOT_FOUND", message="Program version 不存在。", status_code=404
        ) from exc
    except VersionHistoryIntegrityError as exc:
        raise AppError(
            code="VERSION_HISTORY_INTEGRITY_ERROR",
            message="版本历史数据暂时不可用。",
            status_code=409,
        ) from exc


@router.get("/programs/{program_id}/versions", response_model=InternalVersionList)
def list_versions(
    program_id: str,
    session: Annotated[Session, Depends(phase3_session)],
) -> InternalVersionList:
    return _read(lambda: VersionHistoryRepository(session).list_versions(program_id))


@router.get(
    "/program-versions/{version_id}", response_model=InternalVersionRecord
)
def get_version(
    version_id: str,
    session: Annotated[Session, Depends(phase3_session)],
) -> InternalVersionRecord:
    return _read(lambda: VersionHistoryRepository(session).get_version(version_id))


@router.get(
    "/program-versions/{version_id}/diff", response_model=InternalVersionDiff
)
def get_version_diff(
    version_id: str,
    session: Annotated[Session, Depends(phase3_session)],
) -> InternalVersionDiff:
    return _read(lambda: VersionHistoryRepository(session).get_diff(version_id))


@router.get(
    "/programs/{program_id}/audit-events", response_model=AuditTimelineRecord
)
def get_audit_timeline(
    program_id: str,
    session: Annotated[Session, Depends(phase3_session)],
) -> AuditTimelineRecord:
    return _read(
        lambda: VersionHistoryRepository(session).get_audit_timeline(program_id)
    )
