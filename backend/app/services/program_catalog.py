from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from backend.app.schemas.alpha_program_pack import AlphaProgramPackV1
from backend.app.schemas.evidence import derive_evidence_freshness
from backend.app.schemas.internal_alpha import InternalAlphaProgram
from backend.app.schemas.program_catalog import (
    ProgramCatalogDataset,
    ProgramCatalogDetail,
    ProgramCatalogDetailResponse,
    ProgramCatalogField,
    ProgramCatalogItem,
    ProgramCatalogListResponse,
    ProgramCoverageSummary,
    ProgramFieldCitation,
)
from backend.app.schemas.program_fields import CoverageStatus
from backend.app.services.internal_alpha_quality import (
    InternalAlphaQualityContext,
    InternalAlphaQualityInputError,
    internal_alpha_manifest_hash,
    load_internal_alpha_quality_context,
)


DEFAULT_ALPHA_ROOT = Path(__file__).resolve().parents[2] / "data" / "alpha_v1"

FIELD_PRESENTATION: dict[str, tuple[str, str]] = {
    "catalog.academic_year": ("入学年份", "项目概况"),
    "catalog.degree_type": ("学位类型", "项目概况"),
    "catalog.department": ("院系", "项目概况"),
    "catalog.duration": ("学制", "项目概况"),
    "catalog.intake": ("入学时间", "项目概况"),
    "catalog.application_status": ("申请状态", "项目概况"),
    "taxonomy.primary_direction": ("主方向", "专业方向"),
    "taxonomy.secondary_directions": ("相关方向", "专业方向"),
    "taxonomy.low_altitude_basis": ("低空经济归类依据", "专业方向"),
    "requirements.degree": ("学历要求", "申请门槛"),
    "requirements.academic": ("成绩要求", "申请门槛"),
    "requirements.subject": ("本科专业要求", "申请门槛"),
    "requirements.prerequisite_courses": ("先修课程", "申请门槛"),
    "requirements.language": ("语言要求", "申请门槛"),
    "requirements.work_experience": ("工作经验", "申请门槛"),
    "requirements.materials": ("申请材料", "申请门槛"),
}
FIELD_ORDER = {key: index for index, key in enumerate(FIELD_PRESENTATION)}


class ProgramCatalogDataError(ValueError):
    pass


class ProgramCatalogNotFoundError(LookupError):
    pass


class ProgramCatalogService:
    def __init__(
        self,
        *,
        alpha_root: Path = DEFAULT_ALPHA_ROOT,
        clock=lambda: datetime.now(UTC),
    ) -> None:
        self.alpha_root = alpha_root
        self.clock = clock

    def list_programs(self) -> ProgramCatalogListResponse:
        context = self._load_context()
        items = [
            self._item(context.packs_by_ref[entry.pack_ref], entry)
            for entry in context.manifest.programs
        ]
        items.sort(key=lambda item: (item.region.value, item.institution_name, item.official_name))
        return ProgramCatalogListResponse(
            schema_version="program_catalog_list.v1",
            dataset=self._dataset(context),
            programs=items,
        )

    def get_program(self, program_ref: str) -> ProgramCatalogDetailResponse:
        context = self._load_context()
        entry = next(
            (item for item in context.manifest.programs if item.program_ref == program_ref),
            None,
        )
        if entry is None:
            raise ProgramCatalogNotFoundError(program_ref)
        pack = context.packs_by_ref[entry.pack_ref]
        item = self._item(pack, entry)
        evidence_by_id = {item.id: item for item in pack.evidence}
        now = self.clock()
        fields: list[ProgramCatalogField] = []
        for field in pack.candidate.fields:
            presentation = FIELD_PRESENTATION.get(field.field_key)
            if presentation is None:
                raise ProgramCatalogDataError(f"unknown catalog field: {field.field_key}")
            citations = []
            for link in sorted(field.evidence_links, key=lambda value: value.citation_order):
                evidence = evidence_by_id.get(link.evidence_id)
                if evidence is None:
                    raise ProgramCatalogDataError(
                        f"field evidence is missing: {field.field_key}/{link.evidence_id}"
                    )
                citations.append(
                    ProgramFieldCitation(
                        evidence_id=evidence.id,
                        support_scope=link.support_scope.value,
                        citation_order=link.citation_order,
                        url=evidence.url,
                        page_title=evidence.page_title,
                        excerpt=evidence.excerpt,
                        source_version=evidence.source_version,
                        verified_at=evidence.verified_at,
                        review_due_at=evidence.review_due_at,
                        expires_at=evidence.expires_at,
                        freshness=derive_evidence_freshness(
                            availability=evidence.availability_at_verification,
                            review_due_at=evidence.review_due_at,
                            expires_at=evidence.expires_at,
                            now=now,
                        ),
                    )
                )
            fields.append(
                ProgramCatalogField(
                    field_key=field.field_key,
                    label=presentation[0],
                    group=presentation[1],
                    display_text=field.display_text,
                    coverage_status=field.value_payload.coverage_status,
                    is_critical=field.is_critical,
                    value_schema_version=field.value_schema_version,
                    citations=citations,
                )
            )
        fields.sort(key=lambda field: FIELD_ORDER[field.field_key])
        return ProgramCatalogDetailResponse(
            schema_version="program_catalog_detail.v1",
            dataset=self._dataset(context),
            program=ProgramCatalogDetail(**item.model_dump(), fields=fields),
        )

    def _load_context(self) -> InternalAlphaQualityContext:
        try:
            context = load_internal_alpha_quality_context(
                root=self.alpha_root,
                generated_commit="program-catalog-read",
            )
        except InternalAlphaQualityInputError as exc:
            raise ProgramCatalogDataError("internal Alpha dataset cannot be loaded") from exc
        manifest = context.manifest
        if manifest.manifest_sha256 != internal_alpha_manifest_hash(manifest):
            raise ProgramCatalogDataError("internal Alpha manifest hash mismatch")
        for entry in manifest.programs:
            pack = context.packs_by_ref.get(entry.pack_ref)
            if (
                pack is None
                or context.pack_file_sha256_by_ref.get(entry.pack_ref) != entry.pack_file_sha256
                or pack.pack_ref != entry.pack_ref
                or pack.program.program_ref != entry.program_ref
                or pack.pack_canonical_sha256 != entry.pack_canonical_sha256
                or pack.expected_semantic_content_sha256 != entry.candidate_semantic_sha256
            ):
                raise ProgramCatalogDataError(f"internal Alpha pack integrity failed: {entry.pack_ref}")
        return context

    @staticmethod
    def _dataset(context: InternalAlphaQualityContext) -> ProgramCatalogDataset:
        manifest = context.manifest
        return ProgramCatalogDataset(
            dataset_id=manifest.dataset_id,
            target_academic_year=manifest.target_academic_year,
            program_count=manifest.program_count,
            data_boundary=manifest.use_boundary,
            public_publishable=manifest.public_publishable,
            manifest_sha256=manifest.manifest_sha256,
        )

    @staticmethod
    def _item(pack: AlphaProgramPackV1, entry: InternalAlphaProgram) -> ProgramCatalogItem:
        fields = {field.field_key: field for field in pack.candidate.fields}
        primary = fields["taxonomy.primary_direction"].value_payload.value.direction
        secondary = fields["taxonomy.secondary_directions"].value_payload.value.directions
        coverage_counts = Counter(
            field.value_payload.coverage_status for field in pack.candidate.fields
        )
        confirmed = coverage_counts[CoverageStatus.CONFIRMED]
        total = len(pack.candidate.fields)
        return ProgramCatalogItem(
            program_ref=pack.program.program_ref,
            official_name=pack.program.official_name,
            institution_name=pack.program.institution_name,
            region=pack.program.region,
            official_program_url=pack.program.official_program_url,
            target_academic_year=pack.target_academic_year,
            degree_type=pack.program.degree_type,
            primary_direction=primary,
            secondary_directions=secondary,
            review_status="domain_reviewed",
            has_unresolved_fields=confirmed != total,
            reviewed_at=pack.review.reviewed_at,
            candidate_version_id=entry.candidate_version_id,
            pack_ref=pack.pack_ref,
            pack_schema_version=pack.schema_version,
            pack_canonical_sha256=pack.pack_canonical_sha256,
            evidence_count=len(pack.evidence),
            coverage=ProgramCoverageSummary(
                confirmed=confirmed,
                unresolved=total - confirmed,
                total=total,
            ),
        )
