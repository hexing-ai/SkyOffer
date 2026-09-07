from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import (
    EvidenceSupportScope,
    FieldEvidenceLink,
    Program,
    ProgramFieldValue,
    ProgramPublication,
    ProgramVersion,
    SourceEvidence,
    VersionStatus,
)
from backend.app.repositories.candidates import CandidateRepository
from backend.app.schemas.candidates import parse_program_field_payload
from backend.app.schemas.evidence import (
    derive_evidence_freshness,
    normalize_aware_utc,
)
from backend.app.schemas.published_programs import (
    PublishedEvidenceCitation,
    PublishedEvidenceCitationV2,
    PublishedProgramRecord,
    parse_published_program_field,
)
from backend.app.schemas.program_fields import (
    CoverageStatus,
    ProgramRequirementFieldV2,
)


Clock = Callable[[], datetime]


class PublishedProgramReadError(RuntimeError):
    pass


class PublishedProgramNotFoundError(PublishedProgramReadError):
    pass


class ProgramNotPublishedError(PublishedProgramReadError):
    pass


class PublicationIntegrityError(PublishedProgramReadError):
    pass


class PublishedProgramReader:
    def __init__(self, session: Session, *, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    def get(self, program_id: str) -> PublishedProgramRecord:
        program = self._session.get(Program, program_id)
        if program is None:
            raise PublishedProgramNotFoundError("Program 不存在。")
        publication = self._session.get(ProgramPublication, program_id)
        if publication is None:
            raise ProgramNotPublishedError("Program 尚未发布。")
        version = self._session.get(ProgramVersion, publication.current_version_id)
        if (
            version is None
            or version.program_id != program_id
            or version.status != VersionStatus.PUBLISHED
            or version.published_at is None
        ):
            raise PublicationIntegrityError("Current publication pointer 无效。")

        candidate_repository = CandidateRepository(
            self._session,
            clock=self._clock,
            id_factory=lambda _kind: "unused.read-only",
        )
        if not candidate_repository.content_hash_is_valid(version.id):
            raise PublicationIntegrityError("Current published 内容哈希无效。")

        fields = self._session.scalars(
            select(ProgramFieldValue)
            .where(ProgramFieldValue.program_version_id == version.id)
            .order_by(ProgramFieldValue.field_key)
        ).all()
        if not fields or not any(field.is_critical for field in fields):
            raise PublicationIntegrityError("Current published 缺少关键字段。")
        field_ids = [field.id for field in fields]
        links = self._session.scalars(
            select(FieldEvidenceLink)
            .where(FieldEvidenceLink.field_value_id.in_(field_ids))
            .order_by(FieldEvidenceLink.field_value_id, FieldEvidenceLink.citation_order)
        ).all()
        links_by_field: dict[str, list[FieldEvidenceLink]] = {
            field_id: [] for field_id in field_ids
        }
        for link in links:
            links_by_field[link.field_value_id].append(link)
        evidence_ids = sorted({link.evidence_id for link in links})
        evidence_records = self._session.scalars(
            select(SourceEvidence).where(SourceEvidence.id.in_(evidence_ids))
        ).all()
        evidence = {record.id: record for record in evidence_records}
        now = normalize_aware_utc(self._clock())

        try:
            public_fields = []
            for field in fields:
                payload = parse_program_field_payload(
                    field.value_schema_version, field.value_payload
                )
                field_links = links_by_field.get(field.id, [])
                coverage_not_found = (
                    isinstance(payload, ProgramRequirementFieldV2)
                    and payload.coverage_status
                    == CoverageStatus.NOT_FOUND_IN_REVIEWED_SOURCES
                )
                has_required_scope = any(
                    link.support_scope
                    == (
                        EvidenceSupportScope.COVERAGE
                        if coverage_not_found
                        else EvidenceSupportScope.DIRECT
                    )
                    for link in field_links
                )
                if not field_links or (field.is_critical and not has_required_scope):
                    raise PublicationIntegrityError(
                        "Current published 字段证据不完整。"
                    )
                citations = []
                for link in field_links:
                    source = evidence.get(link.evidence_id)
                    if source is None or source.program_id != program_id:
                        raise PublicationIntegrityError(
                            "Current published evidence 归属无效。"
                        )
                    citation_data = {
                        "evidence_id": source.id,
                        "source_type": source.source_type,
                        "url": source.url,
                        "official_domain": source.official_domain,
                        "page_title": source.page_title,
                        "excerpt": source.excerpt,
                        "snapshot_sha256": source.snapshot_sha256,
                        "source_version": source.source_version,
                        "verified_at": source.verified_at,
                        "verified_by": source.verified_by,
                        "review_due_at": source.review_due_at,
                        "expires_at": source.expires_at,
                        "freshness": derive_evidence_freshness(
                            availability=source.availability_at_verification,
                            review_due_at=source.review_due_at,
                            expires_at=source.expires_at,
                            now=now,
                        ),
                        "support_scope": link.support_scope,
                        "citation_order": link.citation_order,
                    }
                    v2_values = (
                        source.capture_method,
                        source.hash_scope,
                        source.reviewed_source_role,
                    )
                    if all(value is None for value in v2_values):
                        citations.append(PublishedEvidenceCitation(**citation_data))
                    elif all(value is not None for value in v2_values):
                        citations.append(
                            PublishedEvidenceCitationV2(
                                **citation_data,
                                schema_version="source_evidence.v2",
                                capture_method=source.capture_method,
                                hash_scope=source.hash_scope,
                                reviewed_source_role=source.reviewed_source_role,
                            )
                        )
                    else:
                        raise PublicationIntegrityError(
                            "Current published Evidence V2 metadata 不完整。"
                        )
                public_fields.append(
                    parse_published_program_field(
                        {
                            "field_key": field.field_key,
                            "value_schema_version": field.value_schema_version,
                            "value_payload": payload,
                            "display_text": field.display_text,
                            "is_critical": field.is_critical,
                            "value_sha256": field.value_sha256,
                            "evidence": citations,
                        }
                    )
                )
            return PublishedProgramRecord(
                program_id=program.id,
                official_name=program.official_name,
                institution_name=program.institution_name,
                region=program.region,
                official_program_url=program.official_program_url,
                version_id=version.id,
                version_no=version.version_no,
                content_schema_version=version.content_schema_version,
                content_sha256=version.content_sha256,
                published_at=version.published_at,
                fields=public_fields,
            )
        except (ValidationError, ValueError) as exc:
            raise PublicationIntegrityError(
                "Current published payload 无法通过公开读取契约。"
            ) from exc
