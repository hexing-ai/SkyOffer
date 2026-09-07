from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import event, func, inspect, select
from sqlalchemy.orm import Session, object_session

from backend.app.db.models import (
    ActorRole,
    AuditEvent,
    AuditEventType,
    FieldEvidenceLink,
    Program,
    ProgramFieldValue,
    ProgramPublication,
    ProgramVersion,
    SourceEvidence,
    VersionStatus,
)
from backend.app.repositories.idempotency import current_idempotency_key_hash
from backend.app.rules.canonical import content_hash, normalize
from backend.app.rules.program_content import (
    CONTENT_SCHEMA_VERSION,
    ENGINE_CONTRACT_VERSION,
    field_fact_projection,
    field_value_hash,
    program_content_envelope,
)
from backend.app.schemas.candidates import (
    CandidateCreate,
    CandidateEvidenceLinkCreate,
    CandidateFieldCreate,
    CandidateRecord,
    FieldDiff,
    FieldDiffSide,
    ProgramFieldPayloadAny,
    ProgramRequirementFieldV1,
    RollbackCandidateCreate,
    parse_candidate_field_create,
    parse_candidate_field_record,
    parse_program_field_payload,
)
from backend.app.schemas.evidence import normalize_aware_utc


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]
class CandidateRepositoryError(RuntimeError):
    pass


class CandidateProgramNotFoundError(CandidateRepositoryError):
    pass


class CandidateStaleBaseError(CandidateRepositoryError):
    pass


class CandidateEvidenceNotFoundError(CandidateRepositoryError):
    pass


class CandidateEvidenceProgramMismatchError(CandidateRepositoryError):
    pass


class CandidateImmutableError(CandidateRepositoryError):
    pass


class CandidateRollbackPublicationRequiredError(CandidateRepositoryError):
    pass


class CandidateRollbackTargetNotFoundError(CandidateRepositoryError):
    pass


class CandidateRollbackTargetProgramMismatchError(CandidateRepositoryError):
    pass


class CandidateRollbackTargetStatusError(CandidateRepositoryError):
    pass


class CandidateRollbackStalePublicationError(CandidateRepositoryError):
    pass


@dataclass(frozen=True, slots=True)
class _FieldSnapshot:
    id: str
    field_key: str
    value_schema_version: str
    value_payload: ProgramFieldPayloadAny
    display_text: str
    is_critical: bool
    value_sha256: str
    evidence_links: tuple[CandidateEvidenceLinkCreate, ...]


_VERSION_CONTENT_COLUMNS = {
    "program_id",
    "version_no",
    "base_version_id",
    "rollback_of_version_id",
    "content_schema_version",
    "content_sha256",
    "created_by",
    "created_at",
}


@event.listens_for(ProgramVersion, "before_update", propagate=True)
def _reject_version_content_update(_mapper, _connection, target) -> None:
    state = inspect(target)
    if any(state.attrs[name].history.has_changes() for name in _VERSION_CONTENT_COLUMNS):
        raise CandidateImmutableError("版本快照内容创建后不可修改。")


@event.listens_for(ProgramVersion, "before_delete", propagate=True)
def _reject_version_delete(_mapper, _connection, _target) -> None:
    raise CandidateImmutableError("版本历史不可删除。")


@event.listens_for(ProgramFieldValue, "before_update", propagate=True)
def _reject_field_update(_mapper, _connection, target) -> None:
    session = object_session(target)
    if session is None or session.is_modified(target, include_collections=False):
        raise CandidateImmutableError("版本字段创建后不可修改。")


@event.listens_for(ProgramFieldValue, "before_delete", propagate=True)
def _reject_field_delete(_mapper, _connection, _target) -> None:
    raise CandidateImmutableError("版本字段不可删除。")


@event.listens_for(FieldEvidenceLink, "before_update", propagate=True)
def _reject_link_update(_mapper, _connection, _target) -> None:
    raise CandidateImmutableError("字段证据链接创建后不可修改。")


@event.listens_for(FieldEvidenceLink, "before_delete", propagate=True)
def _reject_link_delete(_mapper, _connection, _target) -> None:
    raise CandidateImmutableError("字段证据链接不可删除。")


@event.listens_for(Session, "before_flush")
def _reject_snapshot_append(session: Session, _flush_context, _instances) -> None:
    new_version_ids = {
        item.id for item in session.new if isinstance(item, ProgramVersion)
    }
    new_field_ids = {
        item.id for item in session.new if isinstance(item, ProgramFieldValue)
    }
    transaction_version_ids = session.info.setdefault(
        "candidate_new_version_ids", set()
    )
    transaction_field_ids = session.info.setdefault("candidate_new_field_ids", set())
    transaction_version_ids.update(new_version_ids)
    transaction_field_ids.update(new_field_ids)
    for item in session.new:
        if (
            isinstance(item, ProgramFieldValue)
            and item.program_version_id not in transaction_version_ids
        ):
            raise CandidateImmutableError("不能向已有版本追加字段。")
        if (
            isinstance(item, FieldEvidenceLink)
            and item.field_value_id not in transaction_field_ids
        ):
            raise CandidateImmutableError("不能向已有字段追加证据链接。")


def _clear_new_snapshot_ids(session: Session) -> None:
    session.info.pop("candidate_new_version_ids", None)
    session.info.pop("candidate_new_field_ids", None)


@event.listens_for(Session, "after_commit")
def _clear_new_snapshot_ids_after_commit(session: Session) -> None:
    _clear_new_snapshot_ids(session)


@event.listens_for(Session, "after_rollback")
def _clear_new_snapshot_ids_after_rollback(session: Session) -> None:
    _clear_new_snapshot_ids(session)


def _field_fact_projection(payload: ProgramFieldPayloadAny) -> dict[str, Any]:
    return field_fact_projection(payload)


def _value_hash(payload: ProgramFieldPayloadAny) -> str:
    return field_value_hash(payload)


def _evidence_identity(
    links: tuple[CandidateEvidenceLinkCreate, ...],
) -> set[tuple[str, str]]:
    return {
        (
            link.evidence_id,
            link.support_scope.value
            if hasattr(link.support_scope, "value")
            else str(link.support_scope),
        )
        for link in links
    }


def _diff_fields(
    before: dict[str, _FieldSnapshot], after: dict[str, _FieldSnapshot]
) -> list[FieldDiff]:
    result: list[FieldDiff] = []
    for field_key in sorted(set(before) | set(after)):
        old = before.get(field_key)
        new = after.get(field_key)
        old_evidence = _evidence_identity(old.evidence_links) if old else set()
        new_evidence = _evidence_identity(new.evidence_links) if new else set()
        if old is None:
            change_type = "added"
        elif new is None:
            change_type = "removed"
        elif old.value_sha256 != new.value_sha256 or old_evidence != new_evidence:
            change_type = "changed"
        else:
            change_type = "unchanged"
        result.append(
            FieldDiff(
                field_key=field_key,
                change_type=change_type,
                before=(
                    FieldDiffSide(
                        value_sha256=old.value_sha256,
                        display_text=old.display_text,
                    )
                    if old
                    else None
                ),
                after=(
                    FieldDiffSide(
                        value_sha256=new.value_sha256,
                        display_text=new.display_text,
                    )
                    if new
                    else None
                ),
                evidence_added=sorted(
                    evidence_id for evidence_id, _scope in new_evidence - old_evidence
                ),
                evidence_removed=sorted(
                    evidence_id for evidence_id, _scope in old_evidence - new_evidence
                ),
            )
        )
    return result


def _content_envelope(
    fields: dict[str, _FieldSnapshot], evidence: dict[str, SourceEvidence]
) -> dict[str, Any]:
    return program_content_envelope(
        fields.values(),
        {evidence_id: source.snapshot_sha256 for evidence_id, source in evidence.items()},
    )


class CandidateRepository:
    def __init__(self, session: Session, *, clock: Clock, id_factory: IdFactory) -> None:
        self._session = session
        self._clock = clock
        self._id_factory = id_factory

    def create(self, program_id: str, payload: CandidateCreate) -> CandidateRecord:
        return self._create_candidate(
            program_id,
            payload,
            rollback_of_version_id=None,
            audit_event_type=AuditEventType.CREATE,
        )

    def create_rollback(
        self,
        program_id: str,
        target_version_id: str,
        payload: RollbackCandidateCreate,
    ) -> CandidateRecord:
        if self._session.get(Program, program_id) is None:
            raise CandidateProgramNotFoundError("Pilot 项目不存在。")
        publication = self._session.get(ProgramPublication, program_id)
        if publication is None:
            raise CandidateRollbackPublicationRequiredError(
                "项目尚无已发布版本，不能创建 rollback candidate。"
            )
        current_version_id = publication.current_version_id
        if payload.expected_current_version_id != current_version_id:
            raise CandidateRollbackStalePublicationError(
                "expected current version 与实际发布指针不一致。"
            )
        target = self._session.get(ProgramVersion, target_version_id)
        if target is None:
            raise CandidateRollbackTargetNotFoundError("Rollback target 不存在。")
        if target.program_id != program_id:
            raise CandidateRollbackTargetProgramMismatchError(
                "Rollback target 不属于同一项目。"
            )
        if target.status not in {
            VersionStatus.PUBLISHED,
            VersionStatus.SUPERSEDED,
        }:
            raise CandidateRollbackTargetStatusError(
                "Rollback target 必须是 published 或 superseded 历史版本。"
            )

        target_fields = self._load_fields(target.id)
        candidate_payload = CandidateCreate(
            base_version_id=current_version_id,
            fields=[
                parse_candidate_field_create(
                    {
                        "field_key": field.field_key,
                        "value_schema_version": field.value_schema_version,
                        "value_payload": field.value_payload,
                        "display_text": field.display_text,
                        "is_critical": field.is_critical,
                        "evidence_links": list(field.evidence_links),
                    }
                )
                for field in target_fields.values()
            ],
            created_by=payload.created_by,
            creation_note=payload.creation_note,
            request_id=payload.request_id,
        )
        with self._session.begin_nested():
            rollback = self._create_candidate(
                program_id,
                candidate_payload,
                rollback_of_version_id=target.id,
                audit_event_type=AuditEventType.ROLLBACK_CANDIDATE_CREATED,
            )
            if rollback.content_sha256 != target.content_sha256:
                raise CandidateRepositoryError(
                    "Rollback candidate 内容哈希与目标历史版本不一致。"
                )
        return rollback

    def _create_candidate(
        self,
        program_id: str,
        payload: CandidateCreate,
        *,
        rollback_of_version_id: str | None,
        audit_event_type: AuditEventType,
    ) -> CandidateRecord:
        if self._session.get(Program, program_id) is None:
            raise CandidateProgramNotFoundError("Pilot 项目不存在。")
        publication = self._session.get(ProgramPublication, program_id)
        current_version_id = publication.current_version_id if publication else None
        if payload.base_version_id != current_version_id:
            raise CandidateStaleBaseError("Candidate base version 与当前发布版本不一致。")

        before = self._load_fields(payload.base_version_id)
        evidence = self._load_and_validate_evidence(program_id, payload.fields)
        now = normalize_aware_utc(self._clock())
        version_id = self._id_factory("version")
        next_version_no = (
            self._session.scalar(
                select(func.max(ProgramVersion.version_no)).where(
                    ProgramVersion.program_id == program_id
                )
            )
            or 0
        ) + 1

        after: dict[str, _FieldSnapshot] = {}
        for field in payload.fields:
            field_id = self._id_factory("field")
            field_snapshot = _FieldSnapshot(
                id=field_id,
                field_key=field.field_key,
                value_schema_version=field.value_schema_version,
                value_payload=field.value_payload,
                display_text=field.display_text,
                is_critical=field.is_critical,
                value_sha256=_value_hash(field.value_payload),
                evidence_links=tuple(field.evidence_links),
            )
            after[field.field_key] = field_snapshot

        candidate_content_hash = content_hash(_content_envelope(after, evidence))
        version = ProgramVersion(
            id=version_id,
            program_id=program_id,
            version_no=next_version_no,
            base_version_id=payload.base_version_id,
            rollback_of_version_id=rollback_of_version_id,
            status=VersionStatus.CANDIDATE,
            content_schema_version=CONTENT_SCHEMA_VERSION,
            content_sha256=candidate_content_hash,
            created_by=payload.created_by,
            submitted_by=None,
            reviewed_by=None,
            review_note=None,
            created_at=now,
            submitted_at=None,
            reviewed_at=None,
            published_at=None,
        )
        self._session.add(version)

        for field in after.values():
            self._session.add(
                ProgramFieldValue(
                    id=field.id,
                    program_version_id=version_id,
                    field_key=field.field_key,
                    value_schema_version=field.value_schema_version,
                    value_payload=normalize(field.value_payload),
                    display_text=field.display_text,
                    is_critical=field.is_critical,
                    value_sha256=field.value_sha256,
                )
            )
            for link in field.evidence_links:
                self._session.add(
                    FieldEvidenceLink(
                        field_value_id=field.id,
                        evidence_id=link.evidence_id,
                        support_scope=link.support_scope,
                        citation_order=link.citation_order,
                    )
                )

        self._session.add(
            AuditEvent(
                id=self._id_factory("audit"),
                program_id=program_id,
                version_id=version_id,
                event_type=audit_event_type,
                actor_ref=payload.created_by,
                actor_role=ActorRole.DATA_PREPARER,
                reason=payload.creation_note,
                request_id=payload.request_id,
                idempotency_key_hash=current_idempotency_key_hash(self._session),
                event_payload={
                    "version_no": next_version_no,
                    "base_version_id": payload.base_version_id,
                    "rollback_of_version_id": rollback_of_version_id,
                    "field_keys": sorted(after),
                    "content_sha256": candidate_content_hash,
                },
                created_at=now,
            )
        )
        self._session.flush()
        return self._record(version, after, _diff_fields(before, after))

    def get(self, version_id: str) -> CandidateRecord | None:
        version = self._session.get(ProgramVersion, version_id)
        if version is None:
            return None
        fields = self._load_fields(version_id)
        before = self._load_fields(version.base_version_id)
        return self._record(version, fields, _diff_fields(before, fields))

    def content_hash_is_valid(self, version_id: str) -> bool:
        version = self._session.get(ProgramVersion, version_id)
        if version is None:
            return False
        try:
            fields = self._load_fields(version_id)
        except (ValidationError, KeyError, ValueError):
            return False
        if any(
            field.value_sha256 != _value_hash(field.value_payload)
            for field in fields.values()
        ):
            return False
        evidence_ids = sorted(
            {
                link.evidence_id
                for field in fields.values()
                for link in field.evidence_links
            }
        )
        evidence_records = self._session.scalars(
            select(SourceEvidence).where(SourceEvidence.id.in_(evidence_ids))
        ).all()
        evidence = {record.id: record for record in evidence_records}
        if set(evidence) != set(evidence_ids):
            return False
        return content_hash(_content_envelope(fields, evidence)) == version.content_sha256

    def _load_and_validate_evidence(
        self, program_id: str, fields: list[CandidateFieldCreate]
    ) -> dict[str, SourceEvidence]:
        evidence_ids = sorted(
            {
                link.evidence_id
                for field in fields
                for link in field.evidence_links
            }
        )
        if not evidence_ids:
            return {}
        records = self._session.scalars(
            select(SourceEvidence).where(SourceEvidence.id.in_(evidence_ids))
        ).all()
        evidence = {record.id: record for record in records}
        missing = sorted(set(evidence_ids) - set(evidence))
        if missing:
            raise CandidateEvidenceNotFoundError(
                f"Candidate 引用了不存在的 evidence：{', '.join(missing)}"
            )
        mismatched = sorted(
            evidence_id
            for evidence_id, record in evidence.items()
            if record.program_id != program_id
        )
        if mismatched:
            raise CandidateEvidenceProgramMismatchError(
                "Candidate evidence 不属于同一项目。"
            )
        return evidence

    def _load_fields(self, version_id: str | None) -> dict[str, _FieldSnapshot]:
        if version_id is None:
            return {}
        field_values = self._session.scalars(
            select(ProgramFieldValue)
            .where(ProgramFieldValue.program_version_id == version_id)
            .order_by(ProgramFieldValue.field_key)
        ).all()
        if not field_values:
            return {}
        field_ids = [field.id for field in field_values]
        links = self._session.scalars(
            select(FieldEvidenceLink)
            .where(FieldEvidenceLink.field_value_id.in_(field_ids))
            .order_by(FieldEvidenceLink.field_value_id, FieldEvidenceLink.citation_order)
        ).all()
        links_by_field: dict[str, list[CandidateEvidenceLinkCreate]] = {
            field_id: [] for field_id in field_ids
        }
        for link in links:
            links_by_field[link.field_value_id].append(
                CandidateEvidenceLinkCreate(
                    evidence_id=link.evidence_id,
                    support_scope=link.support_scope,
                    citation_order=link.citation_order,
                )
            )
        return {
            field.field_key: _FieldSnapshot(
                id=field.id,
                field_key=field.field_key,
                value_schema_version=field.value_schema_version,
                value_payload=parse_program_field_payload(
                    field.value_schema_version, field.value_payload
                ),
                display_text=field.display_text,
                is_critical=field.is_critical,
                value_sha256=field.value_sha256,
                evidence_links=tuple(links_by_field[field.id]),
            )
            for field in field_values
        }

    @staticmethod
    def _record(
        version: ProgramVersion,
        fields: dict[str, _FieldSnapshot],
        diff: list[FieldDiff],
    ) -> CandidateRecord:
        return CandidateRecord(
            id=version.id,
            program_id=version.program_id,
            version_no=version.version_no,
            base_version_id=version.base_version_id,
            rollback_of_version_id=version.rollback_of_version_id,
            status=version.status,
            content_schema_version=version.content_schema_version,
            content_sha256=version.content_sha256,
            created_by=version.created_by,
            created_at=version.created_at,
            fields=[
                parse_candidate_field_record(
                    {
                        "id": field.id,
                        "field_key": field.field_key,
                        "value_schema_version": field.value_schema_version,
                        "value_payload": field.value_payload,
                        "display_text": field.display_text,
                        "is_critical": field.is_critical,
                        "value_sha256": field.value_sha256,
                        "evidence_links": list(field.evidence_links),
                    }
                )
                for field in fields.values()
            ],
            diff=diff,
        )
