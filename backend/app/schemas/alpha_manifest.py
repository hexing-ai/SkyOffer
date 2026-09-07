from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from backend.app.db.models import ProgramRegion
from backend.app.schemas.evidence import (
    ActorRef,
    Identifier,
    Sha256Hex,
    normalize_aware_utc,
    normalize_official_domain,
    normalize_official_domain_aliases,
    normalize_official_url,
)
from backend.app.schemas.profile_analysis import StrictModel
from backend.app.schemas.program_fields import ProgramDirection


ScopeTemplateState = Literal[
    "empty_unreviewed", "candidate_unreviewed", "frozen_reviewed"
]
ManifestTemplateState = Literal[
    "empty_unreviewed", "candidate_unreviewed", "frozen_reviewed"
]
BlockingReasons = Annotated[list[str], Field(max_length=50)]


class HongKongScopeInstitution(StrictModel):
    institution_ref: Identifier
    official_name: Annotated[str, Field(min_length=1, max_length=300)]
    region: Literal[ProgramRegion.HONG_KONG]
    registered_official_domain: Annotated[str, Field(min_length=3, max_length=253)]
    official_domain_aliases: Annotated[list[str], Field(max_length=10)] = Field(
        default_factory=list
    )

    @field_validator("registered_official_domain")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        return normalize_official_domain(value)

    @model_validator(mode="after")
    def normalize_aliases(self) -> "HongKongScopeInstitution":
        self.official_domain_aliases = normalize_official_domain_aliases(
            self.official_domain_aliases,
            registered_domain=self.registered_official_domain,
        )
        return self


class UnitedKingdomScopeInstitution(StrictModel):
    institution_ref: Identifier
    official_name: Annotated[str, Field(min_length=1, max_length=300)]
    region: Literal[ProgramRegion.UNITED_KINGDOM]
    registered_official_domain: Annotated[str, Field(min_length=3, max_length=253)]
    official_domain_aliases: Annotated[list[str], Field(max_length=10)] = Field(
        default_factory=list
    )
    qs_rank: Annotated[int, Field(ge=1, le=100)]

    @field_validator("registered_official_domain")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        return normalize_official_domain(value)

    @model_validator(mode="after")
    def normalize_aliases(self) -> "UnitedKingdomScopeInstitution":
        self.official_domain_aliases = normalize_official_domain_aliases(
            self.official_domain_aliases,
            registered_domain=self.registered_official_domain,
        )
        return self


class HongKongEightScope(StrictModel):
    scope_name: Literal["hong_kong_eight"]
    institutions: Annotated[list[HongKongScopeInstitution], Field(max_length=8)]

    @model_validator(mode="after")
    def normalize_institutions(self) -> "HongKongEightScope":
        refs = [item.institution_ref for item in self.institutions]
        domains = [item.registered_official_domain for item in self.institutions]
        if len(refs) != len(set(refs)):
            raise ValueError("Hong Kong institution refs must be unique")
        if len(domains) != len(set(domains)):
            raise ValueError("Hong Kong institution domains must be unique")
        self.institutions = sorted(
            self.institutions, key=lambda item: item.institution_ref
        )
        return self


class UnitedKingdomQsScope(StrictModel):
    ranking_provider: Literal["QS"]
    ranking_edition: Literal["2027"]
    source_url: Annotated[str, Field(min_length=1, max_length=2048)] | None
    source_file_sha256: Sha256Hex | None
    institutions: Annotated[list[UnitedKingdomScopeInstitution], Field(max_length=100)]

    @field_validator("source_url")
    @classmethod
    def normalize_source_url(cls, value: str | None) -> str | None:
        return normalize_official_url(value) if value is not None else None

    @model_validator(mode="after")
    def normalize_institutions(self) -> "UnitedKingdomQsScope":
        refs = [item.institution_ref for item in self.institutions]
        domains = [item.registered_official_domain for item in self.institutions]
        if len(refs) != len(set(refs)):
            raise ValueError("United Kingdom institution refs must be unique")
        if len(domains) != len(set(domains)):
            raise ValueError("United Kingdom institution domains must be unique")
        self.institutions = sorted(
            self.institutions, key=lambda item: item.institution_ref
        )
        return self


class AlphaScopeSnapshotV1(StrictModel):
    schema_version: Literal["alpha_scope_snapshot.v1"]
    template_state: ScopeTemplateState
    publishable: bool
    snapshot_id: Identifier | None
    target_academic_year: Literal["2027-28"]
    captured_at: date | None
    reviewed_by: ActorRef | None
    reviewed_at: datetime | None
    hong_kong_eight: HongKongEightScope
    united_kingdom_qs_top_100: UnitedKingdomQsScope
    canonical_sha256: Sha256Hex | None
    blocking_reasons: BlockingReasons

    @field_validator("reviewed_at", mode="after")
    @classmethod
    def normalize_reviewed_at(cls, value: datetime | None) -> datetime | None:
        return normalize_aware_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_state(self) -> "AlphaScopeSnapshotV1":
        all_institutions = [
            *self.hong_kong_eight.institutions,
            *self.united_kingdom_qs_top_100.institutions,
        ]
        refs = [item.institution_ref for item in all_institutions]
        domains = [
            domain
            for item in all_institutions
            for domain in (
                item.registered_official_domain,
                *item.official_domain_aliases,
            )
        ]
        if len(refs) != len(set(refs)):
            raise ValueError("scope institution refs must be globally unique")
        if len(domains) != len(set(domains)) or any(
            left.endswith(f".{right}") or right.endswith(f".{left}")
            for index, left in enumerate(domains)
            for right in domains[index + 1 :]
        ):
            raise ValueError(
                "scope institution registered domains and aliases must be globally unique"
            )
        if len(self.blocking_reasons) != len(set(self.blocking_reasons)):
            raise ValueError("blocking_reasons cannot contain duplicates")
        self.blocking_reasons = sorted(self.blocking_reasons)
        if (
            self.captured_at is not None
            and self.reviewed_at is not None
            and self.reviewed_at.date() < self.captured_at
        ):
            raise ValueError("scope reviewed_at cannot be before captured_at")

        if self.template_state == "empty_unreviewed":
            if self.publishable:
                raise ValueError("empty scope cannot be publishable")
            if all_institutions:
                raise ValueError("empty scope cannot contain institutions")
            if any(
                value is not None
                for value in (
                    self.snapshot_id,
                    self.captured_at,
                    self.reviewed_by,
                    self.reviewed_at,
                    self.united_kingdom_qs_top_100.source_url,
                    self.united_kingdom_qs_top_100.source_file_sha256,
                    self.canonical_sha256,
                )
            ):
                raise ValueError("empty scope must not claim review or hash metadata")
            if not self.blocking_reasons:
                raise ValueError("empty scope must explain why it is blocked")
        elif self.template_state == "candidate_unreviewed":
            if self.publishable or self.canonical_sha256 is not None:
                raise ValueError("candidate scope cannot be publishable or frozen")
            if self.reviewed_by is not None or self.reviewed_at is not None:
                raise ValueError("candidate scope cannot claim completed review")
            candidate_required = (
                self.snapshot_id,
                self.captured_at,
                self.united_kingdom_qs_top_100.source_url,
                self.united_kingdom_qs_top_100.source_file_sha256,
            )
            if (
                not all_institutions
                or not self.blocking_reasons
                or any(value is None for value in candidate_required)
            ):
                raise ValueError(
                    "candidate scope needs entries, source metadata and blocking reasons"
                )
        else:
            required = (
                self.snapshot_id,
                self.captured_at,
                self.reviewed_by,
                self.reviewed_at,
                self.united_kingdom_qs_top_100.source_url,
                self.united_kingdom_qs_top_100.source_file_sha256,
                self.canonical_sha256,
            )
            if not self.publishable or any(value is None for value in required):
                raise ValueError("frozen scope requires complete review and hash metadata")
            if self.blocking_reasons:
                raise ValueError("frozen scope cannot retain blocking reasons")
            if len(self.hong_kong_eight.institutions) != 8:
                raise ValueError("frozen scope must contain exactly the Hong Kong Eight")
            if len(self.united_kingdom_qs_top_100.institutions) < 6:
                raise ValueError("frozen UK scope must contain at least six institutions")
        return self


class FieldRegistryRef(StrictModel):
    path: Literal["program_field_registry.v1.json"]
    schema_version: Literal["program_field_registry.v1"]
    registry_version: Literal["1.0.0"]


class PrimaryDirectionCounts(StrictModel):
    computer_science: Annotated[int, Field(ge=0, le=30)]
    artificial_intelligence: Annotated[int, Field(ge=0, le=30)]
    aerospace_engineering: Annotated[int, Field(ge=0, le=30)]
    low_altitude_economy: Annotated[int, Field(ge=0, le=30)]

    def value_for(self, direction: ProgramDirection) -> int:
        return int(getattr(self, direction.value))


class AlphaSamplePlan(StrictModel):
    target_program_count: Literal[24]
    minimum_program_count: Literal[20]
    maximum_program_count: Literal[30]
    minimum_hong_kong_programs: Literal[8]
    minimum_united_kingdom_programs: Literal[8]
    minimum_hong_kong_institutions: Literal[4]
    minimum_united_kingdom_institutions: Literal[6]
    maximum_programs_per_institution: Literal[4]
    minimum_primary_direction_counts: PrimaryDirectionCounts

    @model_validator(mode="after")
    def validate_direction_minimums(self) -> "AlphaSamplePlan":
        if any(
            self.minimum_primary_direction_counts.value_for(direction) != 4
            for direction in ProgramDirection
        ):
            raise ValueError("each primary direction minimum must remain four")
        return self


class AlphaReviewPlan(StrictModel):
    data_preparer: Literal["actor.data_preparer.codex"]
    domain_reviewer: Literal["actor.domain_reviewer.product_owner"]
    programs_per_review_batch: Literal[3]
    blind_sample_minimum_count: Literal[6]
    blind_sample_rate: Annotated[Decimal, Field(gt=0, le=1)]
    blind_sample_seed_source: Literal["manifest_sha256"]

    @model_validator(mode="after")
    def validate_blind_sample_rate(self) -> "AlphaReviewPlan":
        if self.blind_sample_rate != Decimal("0.25"):
            raise ValueError("blind sample rate must remain 0.25")
        return self


class AlphaManifestProgram(StrictModel):
    pack_ref: Identifier
    pack_path: Annotated[str, Field(min_length=1, max_length=240)]
    pack_sha256: Sha256Hex
    program_ref: Identifier
    institution_ref: Identifier
    region: ProgramRegion
    degree_type: Literal["taught_masters"]
    primary_direction: ProgramDirection
    secondary_directions: Annotated[list[ProgramDirection], Field(max_length=3)]
    replaces_pack_ref: Identifier | None = None
    replacement_reason: Annotated[str, Field(min_length=1, max_length=1000)] | None = None

    @field_validator("pack_path")
    @classmethod
    def validate_pack_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or ".." in path.parts
            or path.parent != PurePosixPath("programs")
            or path.suffix != ".json"
        ):
            raise ValueError("pack_path must be a direct JSON child of programs/")
        return path.as_posix()

    @model_validator(mode="after")
    def validate_program(self) -> "AlphaManifestProgram":
        if PurePosixPath(self.pack_path).stem != self.pack_ref:
            raise ValueError("pack_path filename must equal pack_ref")
        if len(self.secondary_directions) != len(set(self.secondary_directions)):
            raise ValueError("secondary directions cannot contain duplicates")
        if self.primary_direction in self.secondary_directions:
            raise ValueError("primary direction cannot also be secondary")
        self.secondary_directions = sorted(
            self.secondary_directions, key=lambda item: item.value
        )
        if (self.replaces_pack_ref is None) != (self.replacement_reason is None):
            raise ValueError("replacement ref and reason must be provided together")
        if self.replaces_pack_ref == self.pack_ref:
            raise ValueError("a pack cannot replace itself")
        return self


class AlphaMatrixCounts(StrictModel):
    program_count: Annotated[int, Field(ge=0, le=30)]
    hong_kong_programs: Annotated[int, Field(ge=0, le=30)]
    united_kingdom_programs: Annotated[int, Field(ge=0, le=30)]
    hong_kong_institutions: Annotated[int, Field(ge=0, le=8)]
    united_kingdom_institutions: Annotated[int, Field(ge=0, le=100)]
    primary_direction_counts: PrimaryDirectionCounts


class AlphaProgramManifestV1(StrictModel):
    schema_version: Literal["alpha_program_manifest.v1"]
    template_state: ManifestTemplateState
    publishable: bool
    dataset_id: Identifier
    target_academic_year: Literal["2027-28"]
    scope_snapshot_id: Identifier | None
    field_registry: FieldRegistryRef
    sample_plan: AlphaSamplePlan
    review_plan: AlphaReviewPlan
    programs: Annotated[list[AlphaManifestProgram], Field(max_length=30)]
    matrix_counts: AlphaMatrixCounts
    coverage_gaps: Annotated[list[str], Field(default_factory=list, max_length=50)]
    manifest_sha256: Sha256Hex | None
    frozen_by: ActorRef | None
    frozen_at: datetime | None
    blocking_reasons: BlockingReasons

    @field_validator("frozen_at", mode="after")
    @classmethod
    def normalize_frozen_at(cls, value: datetime | None) -> datetime | None:
        return normalize_aware_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_manifest(self) -> "AlphaProgramManifestV1":
        identity_fields = {
            "pack_ref": [item.pack_ref for item in self.programs],
            "pack_path": [item.pack_path for item in self.programs],
            "program_ref": [item.program_ref for item in self.programs],
        }
        for name, values in identity_fields.items():
            if len(values) != len(set(values)):
                raise ValueError(f"manifest {name} values must be unique")
        if len(self.blocking_reasons) != len(set(self.blocking_reasons)):
            raise ValueError("blocking_reasons cannot contain duplicates")
        if len(self.coverage_gaps) != len(set(self.coverage_gaps)):
            raise ValueError("coverage_gaps cannot contain duplicates")
        self.programs = sorted(self.programs, key=lambda item: item.pack_ref)
        self.blocking_reasons = sorted(self.blocking_reasons)
        self.coverage_gaps = sorted(self.coverage_gaps)

        expected = derive_matrix_counts(self.programs)
        if self.matrix_counts != expected:
            raise ValueError("matrix_counts must equal counts derived from programs")

        if self.template_state == "empty_unreviewed":
            if self.publishable or self.programs:
                raise ValueError("empty manifest cannot be publishable or contain programs")
            if any(
                value is not None
                for value in (
                    self.scope_snapshot_id,
                    self.manifest_sha256,
                    self.frozen_by,
                    self.frozen_at,
                )
            ):
                raise ValueError("empty manifest must not claim freeze metadata")
            if not self.blocking_reasons:
                raise ValueError("empty manifest must explain why it is blocked")
        elif self.template_state == "candidate_unreviewed":
            if (
                self.publishable
                or self.manifest_sha256 is not None
                or self.frozen_by is not None
                or self.frozen_at is not None
            ):
                raise ValueError("candidate manifest cannot be publishable or frozen")
            if not self.programs or self.scope_snapshot_id is None:
                raise ValueError("candidate manifest requires programs and a scope ref")
            if not self.blocking_reasons:
                raise ValueError("candidate manifest must retain blocking reasons")
        else:
            if (
                not self.publishable
                or self.scope_snapshot_id is None
                or self.manifest_sha256 is None
                or self.frozen_by is None
                or self.frozen_at is None
            ):
                raise ValueError("frozen manifest requires complete freeze metadata")
            if self.blocking_reasons:
                raise ValueError("frozen manifest cannot retain blocking reasons")
            self._validate_frozen_matrix()
        return self

    def _validate_frozen_matrix(self) -> None:
        counts = self.matrix_counts
        plan = self.sample_plan
        if not plan.minimum_program_count <= counts.program_count <= plan.maximum_program_count:
            raise ValueError("frozen manifest program count must be between 20 and 30")
        if counts.hong_kong_programs < plan.minimum_hong_kong_programs:
            raise ValueError("frozen manifest has too few Hong Kong programs")
        if counts.united_kingdom_programs < plan.minimum_united_kingdom_programs:
            raise ValueError("frozen manifest has too few United Kingdom programs")
        if counts.hong_kong_institutions < plan.minimum_hong_kong_institutions:
            raise ValueError("frozen manifest has too few Hong Kong institutions")
        if counts.united_kingdom_institutions < plan.minimum_united_kingdom_institutions:
            raise ValueError("frozen manifest has too few United Kingdom institutions")
        by_institution: dict[str, int] = {}
        for program in self.programs:
            by_institution[program.institution_ref] = (
                by_institution.get(program.institution_ref, 0) + 1
            )
        if any(value > plan.maximum_programs_per_institution for value in by_institution.values()):
            raise ValueError("an institution exceeds the maximum program count")
        if any(
            counts.primary_direction_counts.value_for(direction)
            < plan.minimum_primary_direction_counts.value_for(direction)
            for direction in ProgramDirection
        ):
            raise ValueError("frozen manifest does not cover every primary direction")
        if counts.program_count != plan.target_program_count and not self.coverage_gaps:
            raise ValueError("a non-target program count requires explicit coverage_gaps")


def derive_matrix_counts(programs: list[AlphaManifestProgram]) -> AlphaMatrixCounts:
    hong_kong = [item for item in programs if item.region == ProgramRegion.HONG_KONG]
    united_kingdom = [
        item for item in programs if item.region == ProgramRegion.UNITED_KINGDOM
    ]
    direction_counts = {
        direction.value: sum(item.primary_direction == direction for item in programs)
        for direction in ProgramDirection
    }
    return AlphaMatrixCounts(
        program_count=len(programs),
        hong_kong_programs=len(hong_kong),
        united_kingdom_programs=len(united_kingdom),
        hong_kong_institutions=len({item.institution_ref for item in hong_kong}),
        united_kingdom_institutions=len(
            {item.institution_ref for item in united_kingdom}
        ),
        primary_direction_counts=PrimaryDirectionCounts(**direction_counts),
    )
