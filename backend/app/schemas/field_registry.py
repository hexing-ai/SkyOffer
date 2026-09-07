from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from backend.app.schemas.profile_analysis import StrictModel
from backend.app.schemas.program_fields import CoverageStatus, ManualReviewReasonCode


REGISTRY_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "alpha_v1"
    / "program_field_registry.v1.json"
)


class RegistryCondition(StrictModel):
    path: Literal["taxonomy.primary_or_secondary_directions"]
    contains: Literal["low_altitude_economy"]


class RegistryFreshnessClass(StrictModel):
    review_due_after_days: Annotated[int, Field(ge=1, le=365)]
    description: Annotated[str, Field(min_length=1, max_length=500)]


class RegistryFieldDefinition(StrictModel):
    field_key: Annotated[str, Field(pattern=r"^(catalog|requirements|taxonomy)\.[a-z_]+$")]
    field_kind: Literal["catalog", "requirement", "taxonomy"]
    payload_schema_version: Literal[
        "program_catalog_field.v1",
        "program_requirement_field.v2",
        "program_taxonomy_field.v1",
    ]
    presence: Literal["required", "conditional"]
    condition: RegistryCondition | None
    is_critical: bool
    freshness_class: Literal["admissions_90d", "application_status_30d"]
    allowed_coverage_statuses: Annotated[list[CoverageStatus], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_definition(self) -> "RegistryFieldDefinition":
        expected_kind = "requirement" if self.field_key.startswith("requirements.") else self.field_key.split(".", 1)[0]
        if self.field_kind != expected_kind:
            raise ValueError("field_kind must match field_key namespace")
        expected_schema = {
            "catalog": "program_catalog_field.v1",
            "requirement": "program_requirement_field.v2",
            "taxonomy": "program_taxonomy_field.v1",
        }[self.field_kind]
        if self.payload_schema_version != expected_schema:
            raise ValueError("payload schema must match field kind")
        if self.presence == "required" and self.condition is not None:
            raise ValueError("required fields cannot include a condition")
        if self.presence == "conditional" and self.condition is None:
            raise ValueError("conditional fields require a condition")
        if len(self.allowed_coverage_statuses) != len(set(self.allowed_coverage_statuses)):
            raise ValueError("allowed coverage statuses cannot contain duplicates")
        return self


class ProgramFieldRegistry(StrictModel):
    schema_version: Literal["program_field_registry.v1"]
    registry_version: Literal["1.0.0"]
    review_status: Literal["approved"]
    approved_by: Literal["actor.domain_reviewer.product_owner"]
    approved_on: str
    target_academic_year: Literal["2027-28"]
    rules: Annotated[list[str], Field(min_length=4)]
    freshness_classes: dict[str, RegistryFreshnessClass]
    coverage_statuses: list[CoverageStatus]
    manual_review_reason_codes: list[ManualReviewReasonCode]
    evidence_support_scopes: list[Literal["direct", "applicability", "definition", "coverage"]]
    fields: Annotated[list[RegistryFieldDefinition], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_registry(self) -> "ProgramFieldRegistry":
        field_keys = [item.field_key for item in self.fields]
        if len(field_keys) != len(set(field_keys)):
            raise ValueError("registry field keys must be unique")
        if set(self.coverage_statuses) != set(CoverageStatus):
            raise ValueError("registry coverage statuses are incomplete")
        if set(self.manual_review_reason_codes) != set(ManualReviewReasonCode):
            raise ValueError("registry manual review reason codes are incomplete")
        if set(self.evidence_support_scopes) != {"direct", "applicability", "definition", "coverage"}:
            raise ValueError("registry evidence support scopes are incomplete")
        if set(self.freshness_classes) != {"admissions_90d", "application_status_30d"}:
            raise ValueError("registry freshness classes are incomplete")
        return self

    def definition_for(self, field_key: str) -> RegistryFieldDefinition:
        for definition in self.fields:
            if definition.field_key == field_key:
                return definition
        raise ValueError(f"unknown registry field key: {field_key}")


@lru_cache(maxsize=1)
def load_program_field_registry() -> ProgramFieldRegistry:
    with REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        return ProgramFieldRegistry.model_validate(json.load(handle))


def validate_registry_field(
    *, field_key: str, schema_version: str, is_critical: bool, coverage_status: CoverageStatus | None
) -> None:
    if field_key == "requirements.language.ielts" and schema_version == "program_requirement_field.v1":
        if is_critical is not True:
            raise ValueError("Pilot v1 field must remain critical")
        return
    definition = load_program_field_registry().definition_for(field_key)
    if schema_version != definition.payload_schema_version:
        raise ValueError("field key and payload schema are not registered together")
    if is_critical != definition.is_critical:
        raise ValueError("field criticality must match the approved registry")
    if coverage_status is not None and coverage_status not in definition.allowed_coverage_statuses:
        raise ValueError("coverage status is not allowed for this registry field")
