from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from urllib.parse import urlsplit

from sqlalchemy import event, select
from sqlalchemy.orm import Session, object_session

from backend.app.db.models import Program, SourceEvidence
from backend.app.schemas.evidence import (
    SourceEvidenceCreate,
    SourceEvidenceCreateAny,
    SourceEvidenceRecord,
    SourceEvidenceRecordAny,
    SourceEvidenceRecordV2,
    belongs_to_official_domains,
    derive_evidence_freshness,
    normalize_aware_utc,
    normalize_official_domain,
)


Clock = Callable[[], datetime]


class EvidenceRepositoryError(RuntimeError):
    pass


class EvidenceProgramNotFoundError(EvidenceRepositoryError):
    pass


class EvidenceOfficialDomainMismatchError(EvidenceRepositoryError):
    pass


class EvidenceAlreadyExistsError(EvidenceRepositoryError):
    pass


class EvidenceImmutableError(EvidenceRepositoryError):
    pass


@event.listens_for(SourceEvidence, "before_update", propagate=True)
def _reject_evidence_update(_mapper, _connection, target) -> None:
    session = object_session(target)
    if session is None or session.is_modified(target, include_collections=False):
        raise EvidenceImmutableError("官方证据创建后不可修改；请创建新的 evidence record。")


@event.listens_for(SourceEvidence, "before_delete", propagate=True)
def _reject_evidence_delete(_mapper, _connection, _target) -> None:
    raise EvidenceImmutableError("官方证据不可删除。")


class SourceEvidenceRepository:
    def __init__(self, session: Session, *, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    def create(self, payload: SourceEvidenceCreateAny) -> SourceEvidenceRecordAny:
        program = self._session.get(Program, payload.program_id)
        if program is None:
            raise EvidenceProgramNotFoundError("Pilot 项目不存在。")
        url_host = normalize_official_domain(urlsplit(payload.url).hostname or "")
        if (
            url_host != payload.official_domain
            or not belongs_to_official_domains(
                payload.official_domain,
                registered_domain=program.registered_official_domain,
                aliases=program.official_domain_aliases,
            )
        ):
            raise EvidenceOfficialDomainMismatchError("证据来源不属于项目登记官方域名。")
        if self._session.get(SourceEvidence, payload.id) is not None:
            raise EvidenceAlreadyExistsError("Evidence ID 已存在；不可覆盖旧证据。")

        created_at = normalize_aware_utc(self._clock())
        database_payload = payload.model_dump(exclude={"schema_version"})
        evidence = SourceEvidence(
            **database_payload,
            created_at=created_at,
        )
        self._session.add(evidence)
        self._session.flush()
        return self._to_record(evidence, now=created_at)

    def get(self, evidence_id: str) -> SourceEvidenceRecordAny | None:
        evidence = self._session.get(SourceEvidence, evidence_id)
        if evidence is None:
            return None
        return self._to_record(evidence, now=normalize_aware_utc(self._clock()))

    def list_for_program(self, program_id: str) -> list[SourceEvidenceRecordAny]:
        if self._session.get(Program, program_id) is None:
            raise EvidenceProgramNotFoundError("Pilot 项目不存在。")
        evidence_records = self._session.scalars(
            select(SourceEvidence)
            .where(SourceEvidence.program_id == program_id)
            .order_by(SourceEvidence.captured_at, SourceEvidence.id)
        ).all()
        now = normalize_aware_utc(self._clock())
        return [self._to_record(evidence, now=now) for evidence in evidence_records]

    @staticmethod
    def _to_record(evidence: SourceEvidence, *, now: datetime) -> SourceEvidenceRecordAny:
        common = {
            "id": evidence.id,
            "program_id": evidence.program_id,
            "source_type": evidence.source_type,
            "url": evidence.url,
            "official_domain": evidence.official_domain,
            "page_title": evidence.page_title,
            "excerpt": evidence.excerpt,
            "snapshot_sha256": evidence.snapshot_sha256,
            "source_version": evidence.source_version,
            "captured_at": evidence.captured_at,
            "verified_at": evidence.verified_at,
            "verified_by": evidence.verified_by,
            "review_due_at": evidence.review_due_at,
            "expires_at": evidence.expires_at,
            "availability_at_verification": evidence.availability_at_verification,
            "created_at": evidence.created_at,
            "freshness": derive_evidence_freshness(
                availability=evidence.availability_at_verification,
                review_due_at=evidence.review_due_at,
                expires_at=evidence.expires_at,
                now=now,
            ),
        }
        v2_values = (
            evidence.capture_method,
            evidence.hash_scope,
            evidence.reviewed_source_role,
        )
        if all(value is None for value in v2_values):
            return SourceEvidenceRecord.model_validate(common)
        if any(value is None for value in v2_values):
            raise EvidenceRepositoryError("Evidence V2 metadata is incomplete.")
        return SourceEvidenceRecordV2.model_validate(
            {
                **common,
                "schema_version": "source_evidence.v2",
                "capture_method": evidence.capture_method,
                "hash_scope": evidence.hash_scope,
                "reviewed_source_role": evidence.reviewed_source_role,
            }
        )
