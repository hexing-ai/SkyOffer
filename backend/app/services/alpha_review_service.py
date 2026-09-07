from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from urllib.parse import urlsplit

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.app.db.models import (
    EvidenceSupportScope,
    Program,
    ProgramPublication,
    ProgramVersion,
    SourceEvidence,
    VersionStatus,
)
from backend.app.repositories.candidates import CandidateRepository
from backend.app.repositories.evidence import SourceEvidenceRepository
from backend.app.repositories.published_programs import PublishedProgramReader
from backend.app.schemas.alpha_manifest import AlphaManifestProgram
from backend.app.schemas.alpha_review import (
    AlphaReviewEvidence,
    AlphaReviewField,
    AlphaReviewGate,
    AlphaReviewProgramDetail,
    AlphaReviewProgramList,
    AlphaReviewProgramSummary,
    AlphaReviewVersion,
)
from backend.app.schemas.candidates import CandidateRecord, FieldDiff
from backend.app.schemas.evidence import (
    belongs_to_official_domains,
    EvidenceFreshness,
    derive_evidence_freshness,
    normalize_aware_utc,
    normalize_official_domain,
)
from backend.app.schemas.field_registry import (
    ProgramFieldRegistry,
    load_program_field_registry,
)
from backend.app.schemas.program_fields import CoverageStatus, ProgramDirection
from backend.app.services.alpha_low_altitude_validator import (
    AlphaLowAltitudeValidationError,
    AlphaTaxonomyEvidenceLinkView,
    AlphaTaxonomyEvidenceView,
    AlphaTaxonomyFieldView,
    validate_low_altitude_taxonomy,
)
from backend.app.services.alpha_program_pack_validator import (
    AlphaProgramPackValidationError,
    validate_alpha_program_pack,
)
from backend.app.services.alpha_quality_scanner import AlphaQualityScanContext


FIELD_LABELS = {
    "catalog.academic_year": "目标学年",
    "catalog.degree_type": "学位类型",
    "catalog.department": "院系",
    "catalog.duration": "学制",
    "catalog.intake": "入学时间",
    "catalog.application_status": "申请状态",
    "taxonomy.primary_direction": "主方向",
    "taxonomy.secondary_directions": "辅助方向",
    "taxonomy.low_altitude_basis": "低空经济纳入依据",
    "requirements.degree": "学历资格",
    "requirements.academic": "学术成绩",
    "requirements.subject": "专业背景",
    "requirements.prerequisite_courses": "先修课程",
    "requirements.language": "语言要求",
    "requirements.work_experience": "工作经验",
    "requirements.materials": "申请材料",
}

GATE_LABELS = {
    "scope_compliance_rate": "范围与项目身份",
    "field_inventory_completion_rate": "字段清单完整",
    "critical_citation_coverage_rate": "关键字段引用",
    "fresh_evidence_at_publish_rate": "发布时证据新鲜度",
    "four_eye_review_rate": "四眼审核",
    "published_only_isolation_rate": "Published-only 隔离",
    "low_altitude_evidence_coverage_rate": "低空课程证据",
    "pack_to_database_semantic_match_rate": "Pack / 数据库一致",
}


class AlphaReviewError(ValueError):
    pass


class AlphaReviewDatasetNotFoundError(AlphaReviewError):
    pass


class AlphaReviewProgramNotFoundError(AlphaReviewError):
    pass


class AlphaReviewVersionNotFoundError(AlphaReviewError):
    pass


def _expected_keys(
    entry: AlphaManifestProgram, registry: ProgramFieldRegistry
) -> set[str]:
    keys = {
        definition.field_key
        for definition in registry.fields
        if definition.presence == "required"
    }
    if ProgramDirection.LOW_ALTITUDE_ECONOMY in {
        entry.primary_direction,
        *entry.secondary_directions,
    }:
        keys.add("taxonomy.low_altitude_basis")
    return keys


def _required_scope(coverage: CoverageStatus | None) -> EvidenceSupportScope:
    if coverage == CoverageStatus.NOT_FOUND_IN_REVIEWED_SOURCES:
        return EvidenceSupportScope.COVERAGE
    if coverage == CoverageStatus.NOT_APPLICABLE:
        return EvidenceSupportScope.APPLICABILITY
    return EvidenceSupportScope.DIRECT


def _belongs_to_program(record: SourceEvidence, program: Program) -> bool:
    try:
        host = normalize_official_domain(urlsplit(record.url).hostname or "")
        domain_matches = belongs_to_official_domains(
            host,
            registered_domain=program.registered_official_domain,
            aliases=program.official_domain_aliases,
        )
    except ValueError:
        return False
    return (
        record.program_id == program.id
        and bool(record.verified_by.strip())
        and record.verified_at is not None
        and domain_matches
    )


def _gate(name: str, status: str, detail: str) -> AlphaReviewGate:
    return AlphaReviewGate(
        name=name,
        label=GATE_LABELS[name],
        status=status,
        detail=detail,
        blocking=status == "block",
    )


class AlphaReviewService:
    def __init__(
        self,
        session: Session,
        *,
        clock,
        registry: ProgramFieldRegistry | None = None,
    ) -> None:
        self._session = session
        self._clock = clock
        self._registry = registry or load_program_field_registry()

    def list_programs(
        self,
        context: AlphaQualityScanContext,
        *,
        offset: int,
        limit: int,
    ) -> AlphaReviewProgramList:
        entries = sorted(context.manifest.programs, key=lambda item: item.pack_ref)
        summaries = [self._summary(context, entry) for entry in entries[offset : offset + limit]]
        if context.manifest.manifest_sha256 is None or context.scope.snapshot_id is None:
            raise AlphaReviewDatasetNotFoundError("Alpha dataset is not frozen")
        return AlphaReviewProgramList(
            schema_version="alpha_review_program_list.v1",
            dataset_id=context.manifest.dataset_id,
            manifest_sha256=context.manifest.manifest_sha256,
            scope_snapshot_id=context.scope.snapshot_id,
            total=len(entries),
            offset=offset,
            limit=limit,
            programs=summaries,
        )

    def program_detail(
        self,
        context: AlphaQualityScanContext,
        *,
        pack_ref: str,
    ) -> AlphaReviewProgramDetail:
        entry = next(
            (item for item in context.manifest.programs if item.pack_ref == pack_ref),
            None,
        )
        pack = context.packs_by_ref.get(pack_ref)
        if entry is None or pack is None:
            raise AlphaReviewProgramNotFoundError("Alpha Program Pack does not exist")
        if context.manifest.manifest_sha256 is None or context.scope.snapshot_id is None:
            raise AlphaReviewDatasetNotFoundError("Alpha dataset is not frozen")
        program = self._session.get(Program, entry.program_ref)
        if program is None:
            raise AlphaReviewProgramNotFoundError("Program is not imported")
        version = self._matching_version(entry, pack.expected_semantic_content_sha256)
        if version is None:
            raise AlphaReviewVersionNotFoundError("Pack candidate version does not exist")
        candidate = CandidateRepository(
            self._session,
            clock=self._clock,
            id_factory=lambda _kind: "unused.alpha.review",
        ).get(version.id)
        evidence_records = {
            record.id: record
            for record in SourceEvidenceRepository(
                self._session, clock=self._clock
            ).list_for_program(program.id)
        }
        orm_evidence = {
            record.id: record
            for record in self._session.scalars(
                select(SourceEvidence).where(SourceEvidence.program_id == program.id)
            ).all()
        }
        fields = self._review_fields(candidate, evidence_records)
        gates = self._gates(
            context=context,
            entry=entry,
            pack=pack,
            program=program,
            version=version,
            candidate=candidate,
            evidence=orm_evidence,
        )
        publication = self._session.get(ProgramPublication, program.id)
        blocking = any(item.blocking for item in gates)
        preflight_ready = version.status == VersionStatus.PENDING_REVIEW and not blocking
        return AlphaReviewProgramDetail(
            schema_version="alpha_review_program_detail.v1",
            dataset_id=context.manifest.dataset_id,
            manifest_sha256=context.manifest.manifest_sha256,
            scope_snapshot_id=context.scope.snapshot_id,
            generated_at=normalize_aware_utc(self._clock()),
            program=self._summary(context, entry),
            version=AlphaReviewVersion(
                version_id=version.id,
                version_no=version.version_no,
                status=version.status,
                content_sha256=version.content_sha256,
                base_version_id=version.base_version_id,
                submitted_by=version.submitted_by,
                reviewed_by=version.reviewed_by,
                review_note=version.review_note,
                submitted_at=version.submitted_at,
                reviewed_at=version.reviewed_at,
                published_at=version.published_at,
            ),
            current_published_version_id=(
                publication.current_version_id if publication is not None else None
            ),
            expected_field_count=len(_expected_keys(entry, self._registry)),
            critical_field_count=sum(item.is_critical for item in fields),
            reviewed_field_count=0,
            fields=fields,
            gates=gates,
            preflight_ready=preflight_ready,
            can_publish=preflight_ready,
            can_reject=version.status == VersionStatus.PENDING_REVIEW,
            reviewer_actor="actor.domain_reviewer.product_owner",
            boundary_notice=(
                "人工数据质检 · 无抓取 · 无模型 · 无推荐 · 非正式运营后台"
            ),
        )

    def _matching_version(self, entry: AlphaManifestProgram, semantic_hash: str):
        return self._session.scalar(
            select(ProgramVersion)
            .where(
                ProgramVersion.program_id == entry.program_ref,
                ProgramVersion.content_sha256 == semantic_hash,
            )
            .order_by(desc(ProgramVersion.version_no))
            .limit(1)
        )

    def _summary(
        self,
        context: AlphaQualityScanContext,
        entry: AlphaManifestProgram,
    ) -> AlphaReviewProgramSummary:
        pack = context.packs_by_ref[entry.pack_ref]
        version = self._matching_version(entry, pack.expected_semantic_content_sha256)
        return AlphaReviewProgramSummary(
            pack_ref=entry.pack_ref,
            program_ref=entry.program_ref,
            official_name=pack.program.official_name,
            institution_name=pack.program.institution_name,
            region=entry.region,
            primary_direction=entry.primary_direction,
            secondary_directions=entry.secondary_directions,
            version_id=version.id if version is not None else None,
            status=version.status if version is not None else "missing",
        )

    def _review_fields(
        self,
        candidate: CandidateRecord,
        evidence_records: Mapping[str, object],
    ) -> list[AlphaReviewField]:
        diff_by_key = {item.field_key: item for item in candidate.diff}
        result: list[AlphaReviewField] = []
        for field in candidate.fields:
            linked: list[AlphaReviewEvidence] = []
            for link in field.evidence_links:
                evidence = evidence_records.get(link.evidence_id)
                if evidence is None or not hasattr(evidence, "hash_scope"):
                    raise AlphaReviewError("Review Evidence V2 is incomplete")
                linked.append(
                    AlphaReviewEvidence(
                        evidence_id=evidence.id,
                        support_scope=link.support_scope,
                        citation_order=link.citation_order,
                        url=evidence.url,
                        page_title=evidence.page_title,
                        excerpt=evidence.excerpt,
                        snapshot_sha256=evidence.snapshot_sha256,
                        hash_scope=evidence.hash_scope,
                        reviewed_source_role=evidence.reviewed_source_role,
                        verified_by=evidence.verified_by,
                        verified_at=evidence.verified_at,
                        review_due_at=evidence.review_due_at,
                        expires_at=evidence.expires_at,
                        freshness=evidence.freshness,
                    )
                )
            diff = diff_by_key.get(field.field_key)
            if diff is None:
                diff = FieldDiff(
                    field_key=field.field_key,
                    change_type="unchanged",
                    before=None,
                    after=None,
                    evidence_added=[],
                    evidence_removed=[],
                )
            coverage = getattr(field.value_payload, "coverage_status", "legacy")
            result.append(
                AlphaReviewField(
                    field_key=field.field_key,
                    display_label=FIELD_LABELS.get(field.field_key, field.field_key),
                    display_text=field.display_text,
                    coverage_status=getattr(coverage, "value", coverage),
                    is_critical=field.is_critical,
                    value_sha256=field.value_sha256,
                    value_payload=field.value_payload.model_dump(mode="json"),
                    diff=diff,
                    evidence=linked,
                )
            )
        return result

    def _gates(
        self,
        *,
        context: AlphaQualityScanContext,
        entry: AlphaManifestProgram,
        pack,
        program: Program,
        version: ProgramVersion,
        candidate: CandidateRecord,
        evidence: Mapping[str, SourceEvidence],
    ) -> list[AlphaReviewGate]:
        gates: list[AlphaReviewGate] = []
        try:
            validate_alpha_program_pack(pack=pack, scope=context.scope, registry=self._registry)
            identity_matches = (
                program.official_name == pack.program.official_name
                and program.institution_name == pack.program.institution_name
                and str(program.region) == pack.program.region.value
                and program.official_program_url == pack.program.official_program_url
                and program.registered_official_domain
                == pack.program.registered_official_domain
                and program.official_domain_aliases
                == pack.program.official_domain_aliases
            )
        except AlphaProgramPackValidationError:
            identity_matches = False
        gates.append(
            _gate(
                "scope_compliance_rate",
                "pass" if identity_matches else "block",
                "Program、冻结 Scope 与 Pack 身份一致。"
                if identity_matches
                else "Program、Scope 或 Pack 身份不一致。",
            )
        )

        fields = {item.field_key: item for item in candidate.fields}
        expected = _expected_keys(entry, self._registry)
        inventory_ok = expected == (expected & set(fields))
        gates.append(
            _gate(
                "field_inventory_completion_rate",
                "pass" if inventory_ok else "block",
                f"已出现 {len(expected & set(fields))} / {len(expected)} 个 mandatory fields。",
            )
        )

        critical = {
            key
            for key in expected
            if self._registry.definition_for(key).is_critical
        }
        qualified = 0
        critical_evidence_ids: set[str] = set()
        for key in critical:
            field = fields.get(key)
            if field is None:
                continue
            coverage = getattr(field.value_payload, "coverage_status", None)
            required = _required_scope(coverage)
            valid_links = [
                link
                for link in field.evidence_links
                if link.support_scope == required
                and (record := evidence.get(link.evidence_id)) is not None
                and _belongs_to_program(record, program)
            ]
            if valid_links:
                qualified += 1
            critical_evidence_ids.update(link.evidence_id for link in field.evidence_links)
        citation_ok = qualified == len(critical)
        gates.append(
            _gate(
                "critical_citation_coverage_rate",
                "pass" if citation_ok else "block",
                f"合格官方引用覆盖 {qualified} / {len(critical)} 个关键字段。",
            )
        )

        now = normalize_aware_utc(self._clock())
        fresh_ok = bool(critical_evidence_ids) and all(
            evidence_id in evidence
            and derive_evidence_freshness(
                availability=evidence[evidence_id].availability_at_verification,
                review_due_at=evidence[evidence_id].review_due_at,
                expires_at=evidence[evidence_id].expires_at,
                now=now,
            )
            == EvidenceFreshness.FRESH
            for evidence_id in critical_evidence_ids
        )
        gates.append(
            _gate(
                "fresh_evidence_at_publish_rate",
                "pass" if fresh_ok else "block",
                "所有关键 Evidence 当前均为 fresh。"
                if fresh_ok
                else "至少一条关键 Evidence 已到期、待复核或不可用。",
            )
        )

        if version.status == VersionStatus.PUBLISHED:
            four_eye_ok = bool(
                version.submitted_by
                and version.reviewed_by
                and version.submitted_by != version.reviewed_by
                and version.review_note
                and version.submitted_at
                and version.reviewed_at
            )
            four_eye_status = "pass" if four_eye_ok else "block"
            four_eye_detail = (
                "提交人与领域复核人分离，审核记录完整。"
                if four_eye_ok
                else "已发布版本的四眼审核元数据不完整。"
            )
        elif version.status == VersionStatus.PENDING_REVIEW:
            four_eye_status = "pending"
            four_eye_detail = "发布动作将由领域复核人完成；当前提交人与复核人分离。"
        else:
            four_eye_status = "pending"
            four_eye_detail = "版本尚未进入可发布的人工复核状态。"
        gates.append(
            _gate("four_eye_review_rate", four_eye_status, four_eye_detail)
        )

        publication = self._session.get(ProgramPublication, program.id)
        if version.status == VersionStatus.PUBLISHED:
            isolated = (
                publication is not None
                and publication.current_version_id == version.id
            )
        else:
            isolated = publication is None or publication.current_version_id != version.id
            if isolated and publication is not None:
                try:
                    isolated = PublishedProgramReader(
                        self._session, clock=self._clock
                    ).get(program.id).version_id != version.id
                except Exception:
                    isolated = False
        gates.append(
            _gate(
                "published_only_isolation_rate",
                "pass" if isolated else "block",
                "待审版本未进入用户 Published-only 读取。"
                if version.status != VersionStatus.PUBLISHED and isolated
                else (
                    "当前发布指针唯一指向该版本。"
                    if isolated
                    else "Published-only 指针或隔离状态异常。"
                ),
            )
        )

        taxonomy_fields = [
            AlphaTaxonomyFieldView(
                field_key=field.field_key,
                is_critical=field.is_critical,
                payload=field.value_payload,
                evidence_links=tuple(
                    AlphaTaxonomyEvidenceLinkView(
                        evidence_id=link.evidence_id,
                        support_scope=link.support_scope,
                    )
                    for link in field.evidence_links
                ),
            )
            for field in candidate.fields
            if field.value_schema_version == "program_taxonomy_field.v1"
        ]
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
            low_report = validate_low_altitude_taxonomy(
                program_ref=program.id,
                fields=taxonomy_fields,
                evidence_by_id=taxonomy_evidence,
            )
            low_ok = (
                low_report.applies
                if ProgramDirection.LOW_ALTITUDE_ECONOMY
                in {entry.primary_direction, *entry.secondary_directions}
                else True
            )
        except AlphaLowAltitudeValidationError:
            low_ok = False
        gates.append(
            _gate(
                "low_altitude_evidence_coverage_rate",
                "pass" if low_ok else "block",
                "低空 basis、课程与 Evidence 完整。"
                if low_ok
                else "低空 basis 或课程 Evidence 未通过独立门禁。",
            )
        )

        semantic_ok = (
            version.content_sha256 == pack.expected_semantic_content_sha256
            and CandidateRepository(
                self._session,
                clock=self._clock,
                id_factory=lambda _kind: "unused.alpha.review.hash",
            ).content_hash_is_valid(version.id)
        )
        gates.append(
            _gate(
                "pack_to_database_semantic_match_rate",
                "pass" if semantic_ok else "block",
                "数据库版本语义 hash 与冻结 Pack 一致。"
                if semantic_ok
                else "数据库版本与冻结 Pack 已发生语义漂移。",
            )
        )
        return gates
