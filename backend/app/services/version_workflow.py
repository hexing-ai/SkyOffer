from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import (
    ActorRole,
    AuditEvent,
    AuditEventType,
    EvidenceSupportScope,
    FieldEvidenceLink,
    ProgramFieldValue,
    ProgramPublication,
    ProgramVersion,
    SourceEvidence,
    VersionStatus,
)
from backend.app.schemas.evidence import (
    EvidenceFreshness,
    derive_evidence_freshness,
    normalize_aware_utc,
)
from backend.app.schemas.candidates import parse_program_field_payload
from backend.app.schemas.program_fields import CoverageStatus, ProgramRequirementFieldV2
from backend.app.schemas.version_workflow import (
    PublishVersionCommand,
    ReviewVersionCommand,
    SubmitVersionCommand,
    VersionTransitionRecord,
)
from backend.app.repositories.idempotency import current_idempotency_key_hash
from backend.app.services.alpha_low_altitude_validator import (
    AlphaLowAltitudeValidationError,
    AlphaTaxonomyEvidenceLinkView,
    AlphaTaxonomyEvidenceView,
    AlphaTaxonomyFieldView,
    validate_low_altitude_taxonomy,
)


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]
FailureHook = Callable[[str], None]


class VersionWorkflowError(RuntimeError):
    pass


class VersionWorkflowNotFoundError(VersionWorkflowError):
    pass


class VersionTransitionInvalidError(VersionWorkflowError):
    pass


class VersionCriticalFieldRequiredError(VersionWorkflowError):
    pass


class VersionEvidenceRequiredError(VersionWorkflowError):
    pass


class VersionDirectEvidenceRequiredError(VersionWorkflowError):
    pass


class VersionEvidenceInvalidError(VersionWorkflowError):
    pass


class VersionEvidenceNotFreshError(VersionWorkflowError):
    pass


class VersionLowAltitudeTaxonomyError(VersionWorkflowError):
    pass


class VersionSelfReviewForbiddenError(VersionWorkflowError):
    pass


class VersionStalePublicationError(VersionWorkflowError):
    pass


class VersionStaleBaseError(VersionWorkflowError):
    pass


class VersionWorkflowService:
    def __init__(
        self,
        session: Session,
        *,
        clock: Clock,
        id_factory: IdFactory,
        failure_hook: FailureHook | None = None,
    ) -> None:
        self._session = session
        self._clock = clock
        self._id_factory = id_factory
        self._failure_hook = failure_hook or (lambda _step: None)

    def submit(
        self, version_id: str, command: SubmitVersionCommand
    ) -> VersionTransitionRecord:
        with self._session.begin_nested():
            version = self._get_version(version_id)
            self._require_status(version, VersionStatus.CANDIDATE)
            self._validate_snapshot_for_submit(version)
            now = normalize_aware_utc(self._clock())
            version.status = VersionStatus.PENDING_REVIEW
            version.submitted_by = command.submitted_by
            version.submitted_at = now
            self._add_audit(
                version=version,
                event_type=AuditEventType.SUBMIT,
                actor_ref=command.submitted_by,
                actor_role=ActorRole.DATA_PREPARER,
                reason=command.submission_note,
                request_id=command.request_id,
                now=now,
            )
            self._failure_hook("after_submit_audit_added")
            self._session.flush()
        return self._record(version)

    def publish(
        self, version_id: str, command: PublishVersionCommand
    ) -> VersionTransitionRecord:
        with self._session.begin_nested():
            version = self._get_version(version_id)
            self._require_status(version, VersionStatus.PENDING_REVIEW)
            self._require_distinct_reviewer(version, command.reviewed_by)
            publication = self._session.get(ProgramPublication, version.program_id)
            current_version_id = (
                publication.current_version_id if publication is not None else None
            )
            if command.expected_current_version_id != current_version_id:
                raise VersionStalePublicationError(
                    "expected current version 与实际发布指针不一致。"
                )
            if version.base_version_id != current_version_id:
                raise VersionStaleBaseError(
                    "待发布版本基于陈旧版本；请重新创建 candidate。"
                )
            now = normalize_aware_utc(self._clock())
            self._validate_snapshot_for_publish(version, now=now)

            if publication is not None:
                previous = self._session.get(
                    ProgramVersion, publication.current_version_id
                )
                if (
                    previous is None
                    or previous.program_id != version.program_id
                    or previous.status != VersionStatus.PUBLISHED
                ):
                    raise VersionStalePublicationError("当前发布指针状态无效。")
                previous.status = VersionStatus.SUPERSEDED
                self._failure_hook("after_old_version_superseded")

            version.status = VersionStatus.PUBLISHED
            version.reviewed_by = command.reviewed_by
            version.review_note = command.review_note
            version.reviewed_at = now
            version.published_at = now
            self._failure_hook("after_new_version_published")

            if publication is None:
                publication = ProgramPublication(
                    program_id=version.program_id,
                    current_version_id=version.id,
                    revision=1,
                    updated_at=now,
                )
                self._session.add(publication)
            else:
                publication.current_version_id = version.id
                publication.revision += 1
                publication.updated_at = now
            self._failure_hook("after_publication_pointer_updated")

            self._add_audit(
                version=version,
                event_type=AuditEventType.PUBLISH,
                actor_ref=command.reviewed_by,
                actor_role=ActorRole.DOMAIN_REVIEWER,
                reason=command.review_note,
                request_id=command.request_id,
                now=now,
                extra_payload={"publication_revision": publication.revision},
            )
            self._failure_hook("after_publish_audit_added")
            self._session.flush()
        return self._record(version)

    def reject(
        self, version_id: str, command: ReviewVersionCommand
    ) -> VersionTransitionRecord:
        with self._session.begin_nested():
            version = self._get_version(version_id)
            self._require_status(version, VersionStatus.PENDING_REVIEW)
            self._require_distinct_reviewer(version, command.reviewed_by)
            now = normalize_aware_utc(self._clock())
            version.status = VersionStatus.REJECTED
            version.reviewed_by = command.reviewed_by
            version.review_note = command.review_note
            version.reviewed_at = now
            self._add_audit(
                version=version,
                event_type=AuditEventType.REJECT,
                actor_ref=command.reviewed_by,
                actor_role=ActorRole.DOMAIN_REVIEWER,
                reason=command.review_note,
                request_id=command.request_id,
                now=now,
            )
            self._failure_hook("after_reject_audit_added")
            self._session.flush()
        return self._record(version)

    def _get_version(self, version_id: str) -> ProgramVersion:
        version = self._session.get(ProgramVersion, version_id)
        if version is None:
            raise VersionWorkflowNotFoundError("Program version 不存在。")
        return version

    @staticmethod
    def _require_status(version: ProgramVersion, expected: VersionStatus) -> None:
        if version.status != expected:
            raise VersionTransitionInvalidError(
                f"非法状态转换：当前状态为 {version.status}，要求 {expected.value}。"
            )

    @staticmethod
    def _require_distinct_reviewer(
        version: ProgramVersion, reviewed_by: str
    ) -> None:
        if version.submitted_by == reviewed_by:
            raise VersionSelfReviewForbiddenError("提交人与领域复核人必须不同。")

    def _validate_snapshot_for_submit(self, version: ProgramVersion) -> None:
        fields = self._load_fields(version.id)
        critical_fields = [field for field in fields if field.is_critical]
        if not critical_fields:
            raise VersionCriticalFieldRequiredError(
                "提交审核前必须至少包含一个关键字段。"
            )
        links = self._load_links(critical_fields)
        for field in critical_fields:
            if not links.get(field.id):
                raise VersionEvidenceRequiredError(
                    f"关键字段 {field.field_key} 缺少官方证据。"
                )

    def _validate_snapshot_for_publish(
        self, version: ProgramVersion, *, now: datetime
    ) -> None:
        fields = self._load_fields(version.id)
        critical_fields = [field for field in fields if field.is_critical]
        if not critical_fields:
            raise VersionCriticalFieldRequiredError(
                "发布前必须至少包含一个关键字段。"
            )
        links = self._load_links(critical_fields)
        evidence_ids = sorted(
            {
                link.evidence_id
                for field_links in links.values()
                for link in field_links
            }
        )
        evidence_records = self._session.scalars(
            select(SourceEvidence).where(SourceEvidence.id.in_(evidence_ids))
        ).all()
        evidence = {record.id: record for record in evidence_records}
        for field in critical_fields:
            field_links = links.get(field.id, [])
            if not field_links:
                raise VersionEvidenceRequiredError(
                    f"关键字段 {field.field_key} 缺少官方证据。"
                )
            payload = parse_program_field_payload(
                field.value_schema_version, field.value_payload
            )
            coverage_not_found = (
                isinstance(payload, ProgramRequirementFieldV2)
                and payload.coverage_status
                == CoverageStatus.NOT_FOUND_IN_REVIEWED_SOURCES
            )
            required_scope = (
                EvidenceSupportScope.COVERAGE
                if coverage_not_found
                else EvidenceSupportScope.DIRECT
            )
            if not any(link.support_scope == required_scope for link in field_links):
                raise VersionDirectEvidenceRequiredError(
                    f"关键字段 {field.field_key} 缺少 {required_scope.value} 官方证据。"
                )
            for link in field_links:
                record = evidence.get(link.evidence_id)
                if (
                    record is None
                    or record.program_id != version.program_id
                    or not record.verified_by.strip()
                    or record.verified_at is None
                ):
                    raise VersionEvidenceInvalidError(
                        f"Evidence {link.evidence_id} 未完成同项目人工核验。"
                    )
                freshness = derive_evidence_freshness(
                    availability=record.availability_at_verification,
                    review_due_at=record.review_due_at,
                    expires_at=record.expires_at,
                    now=now,
                )
                if freshness != EvidenceFreshness.FRESH:
                    raise VersionEvidenceNotFreshError(
                        f"Evidence {link.evidence_id} 当前不是 fresh。"
                    )

        taxonomy_fields = []
        for field in fields:
            if field.value_schema_version != "program_taxonomy_field.v1":
                continue
            taxonomy_fields.append(
                AlphaTaxonomyFieldView(
                    field_key=field.field_key,
                    is_critical=field.is_critical,
                    payload=parse_program_field_payload(
                        field.value_schema_version, field.value_payload
                    ),
                    evidence_links=tuple(
                        AlphaTaxonomyEvidenceLinkView(
                            evidence_id=link.evidence_id,
                            support_scope=link.support_scope,
                        )
                        for link in links.get(field.id, [])
                    ),
                )
            )
        taxonomy_evidence = {
            record.id: AlphaTaxonomyEvidenceView(
                evidence_id=record.id,
                program_ref=record.program_id,
                excerpt=record.excerpt,
                reviewed_source_role=record.reviewed_source_role,
                is_v2=all(
                    value is not None
                    for value in (
                        record.capture_method,
                        record.hash_scope,
                        record.reviewed_source_role,
                    )
                ),
            )
            for record in evidence.values()
        }
        try:
            validate_low_altitude_taxonomy(
                program_ref=version.program_id,
                fields=taxonomy_fields,
                evidence_by_id=taxonomy_evidence,
            )
        except AlphaLowAltitudeValidationError as exc:
            detail = "; ".join(
                f"{issue.code.value}: {issue.message}" for issue in exc.issues
            )
            raise VersionLowAltitudeTaxonomyError(
                f"低空分类未通过发布门禁：{detail}"
            ) from exc

    def _load_fields(self, version_id: str) -> list[ProgramFieldValue]:
        return list(
            self._session.scalars(
                select(ProgramFieldValue)
                .where(ProgramFieldValue.program_version_id == version_id)
                .order_by(ProgramFieldValue.field_key)
            ).all()
        )

    def _load_links(
        self, fields: list[ProgramFieldValue]
    ) -> dict[str, list[FieldEvidenceLink]]:
        field_ids = [field.id for field in fields]
        if not field_ids:
            return {}
        links = self._session.scalars(
            select(FieldEvidenceLink)
            .where(FieldEvidenceLink.field_value_id.in_(field_ids))
            .order_by(FieldEvidenceLink.field_value_id, FieldEvidenceLink.citation_order)
        ).all()
        result: dict[str, list[FieldEvidenceLink]] = {
            field_id: [] for field_id in field_ids
        }
        for link in links:
            result[link.field_value_id].append(link)
        return result

    def _add_audit(
        self,
        *,
        version: ProgramVersion,
        event_type: AuditEventType,
        actor_ref: str,
        actor_role: ActorRole,
        reason: str,
        request_id: str,
        now: datetime,
        extra_payload: dict[str, object] | None = None,
    ) -> None:
        event_payload: dict[str, object] = {
            "version_no": version.version_no,
            "status": version.status,
        }
        if extra_payload:
            event_payload.update(extra_payload)
        self._session.add(
            AuditEvent(
                id=self._id_factory("audit"),
                program_id=version.program_id,
                version_id=version.id,
                event_type=event_type,
                actor_ref=actor_ref,
                actor_role=actor_role,
                reason=reason,
                request_id=request_id,
                idempotency_key_hash=current_idempotency_key_hash(self._session),
                event_payload=event_payload,
                created_at=now,
            )
        )

    def _record(self, version: ProgramVersion) -> VersionTransitionRecord:
        publication = self._session.get(ProgramPublication, version.program_id)
        return VersionTransitionRecord(
            version_id=version.id,
            program_id=version.program_id,
            status=version.status,
            submitted_by=version.submitted_by,
            reviewed_by=version.reviewed_by,
            submitted_at=version.submitted_at,
            reviewed_at=version.reviewed_at,
            published_at=version.published_at,
            current_version_id=(
                publication.current_version_id if publication is not None else None
            ),
            publication_revision=(
                publication.revision if publication is not None else None
            ),
        )
