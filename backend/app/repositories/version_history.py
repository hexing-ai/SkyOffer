from __future__ import annotations

from sqlalchemy import event, select
from sqlalchemy.orm import Session, object_session

from backend.app.db.models import AuditEvent, Program, ProgramVersion
from backend.app.repositories.candidates import CandidateRepository
from backend.app.schemas.version_history import (
    AuditEventRecord,
    AuditTimelineRecord,
    InternalVersionDiff,
    InternalVersionList,
    InternalVersionRecord,
    InternalVersionSummary,
)


class VersionHistoryError(RuntimeError):
    pass


class VersionHistoryProgramNotFoundError(VersionHistoryError):
    pass


class VersionHistoryVersionNotFoundError(VersionHistoryError):
    pass


class VersionHistoryIntegrityError(VersionHistoryError):
    pass


class AuditEventImmutableError(VersionHistoryError):
    pass


@event.listens_for(AuditEvent, "before_update", propagate=True)
def _reject_audit_update(_mapper, _connection, target) -> None:
    session = object_session(target)
    if session is None or session.is_modified(target, include_collections=False):
        raise AuditEventImmutableError("AuditEvent 创建后不可修改。")


@event.listens_for(AuditEvent, "before_delete", propagate=True)
def _reject_audit_delete(_mapper, _connection, _target) -> None:
    raise AuditEventImmutableError("AuditEvent 不可删除。")


class VersionHistoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._candidates = CandidateRepository(
            session,
            clock=lambda: _unused_clock(),
            id_factory=lambda _kind: "unused.read-only",
        )

    def list_versions(self, program_id: str) -> InternalVersionList:
        self._require_program(program_id)
        versions = self._session.scalars(
            select(ProgramVersion)
            .where(ProgramVersion.program_id == program_id)
            .order_by(ProgramVersion.version_no)
        ).all()
        for version in versions:
            self._require_valid_content(version.id)
        return InternalVersionList(
            program_id=program_id,
            versions=[self._summary(version) for version in versions],
        )

    def get_version(self, version_id: str) -> InternalVersionRecord:
        version = self._require_version(version_id)
        self._require_valid_content(version.id)
        candidate = self._candidates.get(version.id)
        if candidate is None:
            raise VersionHistoryVersionNotFoundError("Program version 不存在。")
        return InternalVersionRecord(
            **self._summary(version).model_dump(),
            fields=candidate.fields,
            diff=candidate.diff,
        )

    def get_diff(self, version_id: str) -> InternalVersionDiff:
        version = self.get_version(version_id)
        return InternalVersionDiff(
            version_id=version.id,
            base_version_id=version.base_version_id,
            diff=version.diff,
        )

    def get_audit_timeline(self, program_id: str) -> AuditTimelineRecord:
        self._require_program(program_id)
        events = self._session.scalars(
            select(AuditEvent)
            .where(AuditEvent.program_id == program_id)
            .order_by(AuditEvent.created_at, AuditEvent.id)
        ).all()
        return AuditTimelineRecord(
            program_id=program_id,
            events=[self._audit_record(event) for event in events],
        )

    def _require_program(self, program_id: str) -> Program:
        program = self._session.get(Program, program_id)
        if program is None:
            raise VersionHistoryProgramNotFoundError("Program 不存在。")
        return program

    def _require_version(self, version_id: str) -> ProgramVersion:
        version = self._session.get(ProgramVersion, version_id)
        if version is None:
            raise VersionHistoryVersionNotFoundError("Program version 不存在。")
        return version

    def _require_valid_content(self, version_id: str) -> None:
        if not self._candidates.content_hash_is_valid(version_id):
            raise VersionHistoryIntegrityError("Version content hash 无法重现。")

    @staticmethod
    def _summary(version: ProgramVersion) -> InternalVersionSummary:
        return InternalVersionSummary(
            id=version.id,
            program_id=version.program_id,
            version_no=version.version_no,
            base_version_id=version.base_version_id,
            rollback_of_version_id=version.rollback_of_version_id,
            status=version.status,
            content_schema_version=version.content_schema_version,
            content_sha256=version.content_sha256,
            created_by=version.created_by,
            submitted_by=version.submitted_by,
            reviewed_by=version.reviewed_by,
            review_note=version.review_note,
            created_at=version.created_at,
            submitted_at=version.submitted_at,
            reviewed_at=version.reviewed_at,
            published_at=version.published_at,
        )

    @staticmethod
    def _audit_record(event: AuditEvent) -> AuditEventRecord:
        return AuditEventRecord(
            id=event.id,
            program_id=event.program_id,
            version_id=event.version_id,
            event_type=event.event_type,
            actor_ref=event.actor_ref,
            actor_role=event.actor_role,
            reason=event.reason,
            request_id=event.request_id,
            idempotency_key_hash=event.idempotency_key_hash,
            event_payload=event.event_payload,
            created_at=event.created_at,
        )


def _unused_clock():
    raise RuntimeError("Read-only history repository must not request a clock.")
