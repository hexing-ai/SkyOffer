from __future__ import annotations

from typing import Annotated, Callable, TypeVar

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.api.phase3_dependencies import phase3_session
from backend.app.core.errors import AppError
from backend.app.repositories.candidates import (
    CandidateEvidenceNotFoundError,
    CandidateEvidenceProgramMismatchError,
    CandidateProgramNotFoundError,
    CandidateRepository,
    CandidateRepositoryError,
    CandidateRollbackPublicationRequiredError,
    CandidateRollbackStalePublicationError,
    CandidateRollbackTargetNotFoundError,
    CandidateRollbackTargetProgramMismatchError,
    CandidateRollbackTargetStatusError,
    CandidateStaleBaseError,
)
from backend.app.repositories.evidence import (
    EvidenceAlreadyExistsError,
    EvidenceOfficialDomainMismatchError,
    EvidenceProgramNotFoundError,
    EvidenceRepositoryError,
    SourceEvidenceRepository,
)
from backend.app.repositories.idempotency import (
    IdempotencyConflictError,
    IdempotencyExecutor,
    IdempotencyKeyInvalidError,
)
from backend.app.repositories.programs import (
    ProgramAlreadyExistsError,
    ProgramRepository,
    ProgramRepositoryError,
)
from backend.app.schemas.candidates import (
    CandidateCreate,
    CandidateRecord,
    RollbackCandidateCreate,
)
from backend.app.schemas.evidence import (
    SourceEvidenceCreateAny,
    SourceEvidenceRecordAny,
    SourceEvidenceRecordEnvelope,
)
from backend.app.schemas.phase3_api import (
    CandidateCreateRequest,
    PublishVersionRequest,
    RejectVersionRequest,
    RollbackCandidateRequest,
    SubmitVersionRequest,
    SourceEvidenceList,
)
from backend.app.schemas.programs import ProgramCreateRequest, ProgramRecord
from backend.app.schemas.version_workflow import (
    PublishVersionCommand,
    ReviewVersionCommand,
    SubmitVersionCommand,
    VersionTransitionRecord,
)
from backend.app.services.version_workflow import (
    VersionCriticalFieldRequiredError,
    VersionDirectEvidenceRequiredError,
    VersionEvidenceInvalidError,
    VersionEvidenceNotFreshError,
    VersionEvidenceRequiredError,
    VersionSelfReviewForbiddenError,
    VersionStaleBaseError,
    VersionStalePublicationError,
    VersionTransitionInvalidError,
    VersionWorkflowError,
    VersionWorkflowNotFoundError,
    VersionWorkflowService,
)


router = APIRouter(prefix="/api/v1/internal", tags=["phase-three-internal"])
ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


def _idempotency_key(
    value: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if value is None:
        raise AppError(
            code="IDEMPOTENCY_KEY_REQUIRED",
            message="该写操作必须提供 Idempotency-Key。",
            status_code=400,
        )
    return value


def _translate_error(exc: Exception) -> AppError:
    mappings: list[tuple[type[Exception], str, str, int]] = [
        (
            IdempotencyConflictError,
            "IDEMPOTENCY_CONFLICT",
            "同一 Idempotency-Key 已用于不同请求。",
            409,
        ),
        (
            IdempotencyKeyInvalidError,
            "IDEMPOTENCY_KEY_INVALID",
            "Idempotency-Key 格式无效。",
            400,
        ),
        (EvidenceProgramNotFoundError, "PROGRAM_NOT_FOUND", "项目不存在。", 404),
        (
            EvidenceOfficialDomainMismatchError,
            "OFFICIAL_DOMAIN_MISMATCH",
            "证据来源不属于项目登记官方域名。",
            409,
        ),
        (
            EvidenceAlreadyExistsError,
            "EVIDENCE_ALREADY_EXISTS",
            "Evidence ID 已存在且不可覆盖。",
            409,
        ),
        (CandidateProgramNotFoundError, "PROGRAM_NOT_FOUND", "项目不存在。", 404),
        (
            CandidateStaleBaseError,
            "STALE_BASE_VERSION",
            "Candidate base version 已陈旧。",
            409,
        ),
        (
            CandidateEvidenceNotFoundError,
            "EVIDENCE_NOT_FOUND",
            "Candidate 引用了不存在的证据。",
            404,
        ),
        (
            CandidateEvidenceProgramMismatchError,
            "EVIDENCE_PROGRAM_MISMATCH",
            "Candidate 证据不属于同一项目。",
            409,
        ),
        (
            CandidateRollbackPublicationRequiredError,
            "PROGRAM_NOT_PUBLISHED",
            "项目尚无 current published 版本。",
            409,
        ),
        (
            CandidateRollbackStalePublicationError,
            "STALE_PUBLICATION",
            "Expected current version 已陈旧。",
            409,
        ),
        (
            CandidateRollbackTargetNotFoundError,
            "ROLLBACK_TARGET_NOT_FOUND",
            "Rollback target 不存在。",
            404,
        ),
        (
            CandidateRollbackTargetProgramMismatchError,
            "VERSION_PROGRAM_MISMATCH",
            "Rollback target 不属于同一项目。",
            409,
        ),
        (
            CandidateRollbackTargetStatusError,
            "ROLLBACK_TARGET_INVALID",
            "Rollback target 状态无效。",
            409,
        ),
        (
            VersionWorkflowNotFoundError,
            "VERSION_NOT_FOUND",
            "Program version 不存在。",
            404,
        ),
        (
            VersionTransitionInvalidError,
            "VERSION_TRANSITION_INVALID",
            "当前版本状态不允许该操作。",
            409,
        ),
        (
            VersionSelfReviewForbiddenError,
            "SELF_REVIEW_FORBIDDEN",
            "提交人与领域复核人必须不同。",
            403,
        ),
        (
            VersionCriticalFieldRequiredError,
            "CRITICAL_FIELD_REQUIRED",
            "版本缺少关键字段。",
            409,
        ),
        (
            VersionEvidenceRequiredError,
            "EVIDENCE_REQUIRED",
            "关键字段缺少官方证据。",
            409,
        ),
        (
            VersionDirectEvidenceRequiredError,
            "DIRECT_EVIDENCE_REQUIRED",
            "关键字段缺少 direct 官方证据。",
            409,
        ),
        (
            VersionEvidenceInvalidError,
            "EVIDENCE_NOT_VERIFIED",
            "版本包含未完成同项目人工核验的证据。",
            409,
        ),
        (
            VersionEvidenceNotFreshError,
            "EVIDENCE_NOT_FRESH",
            "版本包含当前不是 fresh 的证据。",
            409,
        ),
        (
            VersionStalePublicationError,
            "STALE_PUBLICATION",
            "Expected current version 已陈旧。",
            409,
        ),
        (
            VersionStaleBaseError,
            "STALE_BASE_VERSION",
            "待发布版本基于陈旧版本。",
            409,
        ),
        (
            ProgramAlreadyExistsError,
            "PROGRAM_ALREADY_EXISTS",
            "该官方项目 URL 已登记。",
            409,
        ),
    ]
    for error_type, code, message, status_code in mappings:
        if isinstance(exc, error_type):
            return AppError(
                code=code,
                message=message,
                status_code=status_code,
            )
    if isinstance(exc, (EvidenceRepositoryError, CandidateRepositoryError)):
        return AppError(
            code="PHASE3_WRITE_REJECTED",
            message="该写操作未通过业务校验。",
            status_code=409,
        )
    if isinstance(exc, VersionWorkflowError):
        return AppError(
            code="VERSION_WORKFLOW_REJECTED",
            message="版本工作流操作未通过业务校验。",
            status_code=409,
        )
    if isinstance(exc, ProgramRepositoryError):
        return AppError(
            code="PROGRAM_WRITE_REJECTED",
            message="Program 写操作未通过业务校验。",
            status_code=409,
        )
    raise exc


def _execute(
    *,
    request: Request,
    session: Session,
    key: str,
    operation_type: str,
    request_payload: object,
    response_model: type[ResponseModel],
    handler: Callable[[], ResponseModel],
    response_status: int,
) -> ResponseModel:
    try:
        return IdempotencyExecutor(
            session,
            clock=request.app.state.phase3_clock,
            id_factory=request.app.state.phase3_id_factory,
        ).execute(
            key=key,
            operation_type=operation_type,
            request_payload=request_payload,
            response_model=response_model,
            handler=handler,
            response_status=response_status,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/programs",
    response_model=ProgramRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_program(
    payload: ProgramCreateRequest,
    request: Request,
    session: Annotated[Session, Depends(phase3_session)],
    key: Annotated[str, Depends(_idempotency_key)],
) -> ProgramRecord:
    return _execute(
        request=request,
        session=session,
        key=key,
        operation_type="program.create",
        request_payload=payload,
        response_model=ProgramRecord,
        handler=lambda: ProgramRepository(
            session,
            clock=request.app.state.phase3_clock,
            id_factory=request.app.state.phase3_id_factory,
        ).create(payload, request_id=request.state.request_id),
        response_status=201,
    )


@router.post(
    "/source-evidence",
    response_model=SourceEvidenceRecordEnvelope,
    status_code=status.HTTP_201_CREATED,
)
def create_source_evidence(
    payload: SourceEvidenceCreateAny,
    request: Request,
    session: Annotated[Session, Depends(phase3_session)],
    key: Annotated[str, Depends(_idempotency_key)],
) -> SourceEvidenceRecordEnvelope:
    return _execute(
        request=request,
        session=session,
        key=key,
        operation_type="source_evidence.create",
        request_payload=payload,
        response_model=SourceEvidenceRecordEnvelope,
        handler=lambda: SourceEvidenceRecordEnvelope(
            root=SourceEvidenceRepository(
                session, clock=request.app.state.phase3_clock
            ).create(payload)
        ),
        response_status=201,
    )


@router.get(
    "/source-evidence/{evidence_id}", response_model=SourceEvidenceRecordAny
)
def get_source_evidence(
    evidence_id: str,
    request: Request,
    session: Annotated[Session, Depends(phase3_session)],
) -> SourceEvidenceRecordAny:
    evidence = SourceEvidenceRepository(
        session, clock=request.app.state.phase3_clock
    ).get(evidence_id)
    if evidence is None:
        raise AppError(
            code="EVIDENCE_NOT_FOUND",
            message="Evidence 不存在。",
            status_code=404,
        )
    return evidence


@router.get(
    "/programs/{program_id}/source-evidence",
    response_model=SourceEvidenceList,
)
def list_source_evidence(
    program_id: str,
    request: Request,
    session: Annotated[Session, Depends(phase3_session)],
) -> SourceEvidenceList:
    try:
        evidence = SourceEvidenceRepository(
            session, clock=request.app.state.phase3_clock
        ).list_for_program(program_id)
    except EvidenceRepositoryError as exc:
        raise _translate_error(exc) from exc
    return SourceEvidenceList(program_id=program_id, evidence=evidence)


@router.post(
    "/programs/{program_id}/versions",
    response_model=CandidateRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_candidate(
    program_id: str,
    payload: CandidateCreateRequest,
    request: Request,
    session: Annotated[Session, Depends(phase3_session)],
    key: Annotated[str, Depends(_idempotency_key)],
) -> CandidateRecord:
    command = CandidateCreate(
        **payload.model_dump(), request_id=request.state.request_id
    )
    return _execute(
        request=request,
        session=session,
        key=key,
        operation_type="candidate.create",
        request_payload={"program_id": program_id, "payload": payload},
        response_model=CandidateRecord,
        handler=lambda: CandidateRepository(
            session,
            clock=request.app.state.phase3_clock,
            id_factory=request.app.state.phase3_id_factory,
        ).create(program_id, command),
        response_status=201,
    )


@router.post(
    "/program-versions/{version_id}/submit",
    response_model=VersionTransitionRecord,
)
def submit_version(
    version_id: str,
    payload: SubmitVersionRequest,
    request: Request,
    session: Annotated[Session, Depends(phase3_session)],
    key: Annotated[str, Depends(_idempotency_key)],
) -> VersionTransitionRecord:
    command = SubmitVersionCommand(
        **payload.model_dump(), request_id=request.state.request_id
    )
    return _execute(
        request=request,
        session=session,
        key=key,
        operation_type="version.submit",
        request_payload={"version_id": version_id, "payload": payload},
        response_model=VersionTransitionRecord,
        handler=lambda: VersionWorkflowService(
            session,
            clock=request.app.state.phase3_clock,
            id_factory=request.app.state.phase3_id_factory,
        ).submit(version_id, command),
        response_status=200,
    )


@router.post(
    "/program-versions/{version_id}/publish",
    response_model=VersionTransitionRecord,
)
def publish_version(
    version_id: str,
    payload: PublishVersionRequest,
    request: Request,
    session: Annotated[Session, Depends(phase3_session)],
    key: Annotated[str, Depends(_idempotency_key)],
) -> VersionTransitionRecord:
    command = PublishVersionCommand(
        **payload.model_dump(), request_id=request.state.request_id
    )
    return _execute(
        request=request,
        session=session,
        key=key,
        operation_type="version.publish",
        request_payload={"version_id": version_id, "payload": payload},
        response_model=VersionTransitionRecord,
        handler=lambda: VersionWorkflowService(
            session,
            clock=request.app.state.phase3_clock,
            id_factory=request.app.state.phase3_id_factory,
        ).publish(version_id, command),
        response_status=200,
    )


@router.post(
    "/program-versions/{version_id}/reject",
    response_model=VersionTransitionRecord,
)
def reject_version(
    version_id: str,
    payload: RejectVersionRequest,
    request: Request,
    session: Annotated[Session, Depends(phase3_session)],
    key: Annotated[str, Depends(_idempotency_key)],
) -> VersionTransitionRecord:
    command = ReviewVersionCommand(
        **payload.model_dump(), request_id=request.state.request_id
    )
    return _execute(
        request=request,
        session=session,
        key=key,
        operation_type="version.reject",
        request_payload={"version_id": version_id, "payload": payload},
        response_model=VersionTransitionRecord,
        handler=lambda: VersionWorkflowService(
            session,
            clock=request.app.state.phase3_clock,
            id_factory=request.app.state.phase3_id_factory,
        ).reject(version_id, command),
        response_status=200,
    )


@router.post(
    "/programs/{program_id}/rollback-candidates",
    response_model=CandidateRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_rollback_candidate(
    program_id: str,
    payload: RollbackCandidateRequest,
    request: Request,
    session: Annotated[Session, Depends(phase3_session)],
    key: Annotated[str, Depends(_idempotency_key)],
) -> CandidateRecord:
    command = RollbackCandidateCreate(
        expected_current_version_id=payload.expected_current_version_id,
        created_by=payload.created_by,
        creation_note=payload.creation_note,
        request_id=request.state.request_id,
    )
    return _execute(
        request=request,
        session=session,
        key=key,
        operation_type="rollback_candidate.create",
        request_payload={"program_id": program_id, "payload": payload},
        response_model=CandidateRecord,
        handler=lambda: CandidateRepository(
            session,
            clock=request.app.state.phase3_clock,
            id_factory=request.app.state.phase3_id_factory,
        ).create_rollback(program_id, payload.target_version_id, command),
        response_status=201,
    )
