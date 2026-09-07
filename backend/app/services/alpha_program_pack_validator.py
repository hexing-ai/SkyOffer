from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import ValidationError

from backend.app.db.models import EvidenceSupportScope
from backend.app.rules.canonical import content_hash
from backend.app.rules.program_content import program_content_hash
from backend.app.schemas.alpha_manifest import AlphaScopeSnapshotV1
from backend.app.schemas.alpha_program_pack import AlphaProgramPackV1
from backend.app.schemas.evidence import (
    Sha256Hex,
    belongs_to_official_domains,
    normalize_official_domain,
)
from backend.app.schemas.field_registry import (
    ProgramFieldRegistry,
    load_program_field_registry,
)
from backend.app.schemas.profile_analysis import StrictModel
from backend.app.schemas.program_fields import CoverageStatus
from backend.app.services.alpha_low_altitude_validator import (
    AlphaLowAltitudeValidationError,
    AlphaTaxonomyEvidenceLinkView,
    AlphaTaxonomyEvidenceView,
    AlphaTaxonomyFieldView,
    validate_low_altitude_taxonomy,
)


class AlphaProgramPackValidationError(ValueError):
    def __init__(self, issues: list[str]) -> None:
        self.issues = tuple(sorted(set(issues)))
        super().__init__("; ".join(self.issues))


class AlphaProgramPackValidationReport(StrictModel):
    schema_version: Literal["alpha_program_pack_validation_report.v1"]
    pack_ref: str
    program_ref: str
    scope_snapshot_id: str
    field_count: int
    evidence_count: int
    computed_pack_canonical_sha256: Sha256Hex
    computed_semantic_content_sha256: Sha256Hex
    valid: Literal[True]


def _pydantic_issues(label: str, exc: ValidationError) -> list[str]:
    return [
        f"{label}.{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors()
    ]


def _read_json(path: Path, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AlphaProgramPackValidationError(
            [f"{label} file cannot be read"]
        ) from exc
    except json.JSONDecodeError as exc:
        raise AlphaProgramPackValidationError([f"{label} is not valid JSON"]) from exc


def alpha_program_pack_hash(pack: AlphaProgramPackV1) -> str:
    return content_hash(
        pack.model_dump(mode="python", exclude={"pack_canonical_sha256"})
    )


def alpha_program_pack_semantic_hash(pack: AlphaProgramPackV1) -> str:
    return program_content_hash(
        pack.candidate.fields,
        {item.id: item.snapshot_sha256 for item in pack.evidence},
    )


def _scope_institution(pack: AlphaProgramPackV1, scope: AlphaScopeSnapshotV1):
    institutions = [
        *scope.hong_kong_eight.institutions,
        *scope.united_kingdom_qs_top_100.institutions,
    ]
    return next(
        (
            item
            for item in institutions
            if item.institution_ref == pack.scope_institution_ref
        ),
        None,
    )


def validate_alpha_program_pack(
    *,
    pack: AlphaProgramPackV1,
    scope: AlphaScopeSnapshotV1,
    registry: ProgramFieldRegistry | None = None,
) -> AlphaProgramPackValidationReport:
    registry = registry or load_program_field_registry()
    issues: list[str] = []

    if scope.template_state != "frozen_reviewed" or not scope.publishable:
        issues.append("scope snapshot must be frozen and publishable")
    if pack.scope_snapshot_id != scope.snapshot_id:
        issues.append("pack scope_snapshot_id does not match the supplied scope")
    if pack.target_academic_year != scope.target_academic_year:
        issues.append("pack academic year does not match scope")
    if pack.target_academic_year != registry.target_academic_year:
        issues.append("pack academic year does not match field registry")

    institution = _scope_institution(pack, scope)
    if institution is None:
        issues.append("pack institution is outside the frozen scope")
    else:
        if pack.program.institution_name != institution.official_name:
            issues.append("program institution name does not match its scope entry")
        if pack.program.region != institution.region:
            issues.append("program region does not match its scope entry")
        if (
            pack.program.registered_official_domain
            != institution.registered_official_domain
        ):
            issues.append("program official domain does not match its scope entry")
        if pack.program.official_domain_aliases != institution.official_domain_aliases:
            issues.append(
                "program official domain aliases do not match its scope entry"
            )

    evidence_by_id = {item.id: item for item in pack.evidence}
    pack_source_ids = set(pack.reviewed_source_ids)
    referenced_source_ids: set[str] = set()
    for evidence in pack.evidence:
        if evidence.applicable_academic_year != pack.target_academic_year:
            issues.append(f"Evidence {evidence.id} has the wrong academic year")
        if evidence.program_id != pack.program.program_ref:
            issues.append(f"Evidence {evidence.id} belongs to another program")
        host = normalize_official_domain(urlsplit(evidence.url).hostname or "")
        if not belongs_to_official_domains(
            host,
            registered_domain=pack.program.registered_official_domain,
            aliases=pack.program.official_domain_aliases,
        ):
            issues.append(f"Evidence {evidence.id} is outside the official domain")
        if evidence.verified_by != pack.review.prepared_by:
            issues.append(f"Evidence {evidence.id} was not verified by the data preparer")

    field_by_key = {item.field_key: item for item in pack.candidate.fields}
    required_keys = {
        item.field_key for item in registry.fields if item.presence == "required"
    }
    actual_keys = set(field_by_key)
    missing = sorted(required_keys - actual_keys)
    if missing:
        issues.append(f"candidate is missing mandatory fields: {', '.join(missing)}")

    for field in pack.candidate.fields:
        payload = field.value_payload
        if getattr(payload, "applicable_academic_year", None) != pack.target_academic_year:
            issues.append(f"field {field.field_key} has the wrong academic year")
        reviewed_ids = set(getattr(payload, "reviewed_source_ids", []))
        linked_ids = {item.evidence_id for item in field.evidence_links}
        referenced_source_ids.update(reviewed_ids)
        referenced_source_ids.update(linked_ids)
        if not reviewed_ids.issubset(pack_source_ids) or not linked_ids.issubset(
            pack_source_ids
        ):
            issues.append(f"field {field.field_key} references Evidence outside the pack")
        coverage = getattr(payload, "coverage_status", None)
        if (
            coverage == CoverageStatus.NOT_FOUND_IN_REVIEWED_SOURCES
            and reviewed_ids != pack_source_ids
        ):
            issues.append(
                f"not-found field {field.field_key} must record the complete reviewed source set"
            )
        if coverage == CoverageStatus.CONFIRMED:
            forbidden = {
                link.support_scope
                for link in field.evidence_links
                if link.support_scope
                in {EvidenceSupportScope.COVERAGE, EvidenceSupportScope.DEFINITION}
            }
            if forbidden:
                issues.append(
                    f"confirmed field {field.field_key} cannot use coverage or definition Evidence"
                )
            direct_excerpts = [
                evidence_by_id[link.evidence_id].excerpt
                for link in field.evidence_links
                if link.support_scope == EvidenceSupportScope.DIRECT
                and link.evidence_id in evidence_by_id
            ]
            is_human_taxonomy_rationale = (
                field.field_key == "taxonomy.low_altitude_basis"
            )
            if not is_human_taxonomy_rationale and not any(
                field.display_text in excerpt for excerpt in direct_excerpts
            ):
                issues.append(
                    f"confirmed field {field.field_key} display_text is not verbatim "
                    "direct Evidence"
                )

    if referenced_source_ids != pack_source_ids:
        issues.append("reviewed source set, Evidence and field references are not closed")

    degree_field = field_by_key.get("catalog.degree_type")
    if (
        degree_field is None
        or degree_field.value_payload.value is None
        or degree_field.value_payload.value.degree_type != pack.program.degree_type
    ):
        issues.append("catalog degree type does not confirm taught_masters")

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
        for field in pack.candidate.fields
        if field.value_schema_version == "program_taxonomy_field.v1"
    ]
    taxonomy_evidence = {
        evidence.id: AlphaTaxonomyEvidenceView(
            evidence_id=evidence.id,
            program_ref=evidence.program_id,
            excerpt=evidence.excerpt,
            reviewed_source_role=evidence.reviewed_source_role,
            is_v2=True,
        )
        for evidence in pack.evidence
    }
    try:
        validate_low_altitude_taxonomy(
            program_ref=pack.program.program_ref,
            fields=taxonomy_fields,
            evidence_by_id=taxonomy_evidence,
        )
    except AlphaLowAltitudeValidationError as exc:
        issues.extend(
            f"{issue.code.value}: {issue.message}" for issue in exc.issues
        )

    computed_semantic = alpha_program_pack_semantic_hash(pack)
    computed_pack = alpha_program_pack_hash(pack)
    if pack.expected_semantic_content_sha256 != computed_semantic:
        issues.append("stored expected semantic content hash does not match computed hash")
    if pack.pack_canonical_sha256 != computed_pack:
        issues.append("stored pack canonical hash does not match computed hash")

    if issues:
        raise AlphaProgramPackValidationError(issues)
    return AlphaProgramPackValidationReport(
        schema_version="alpha_program_pack_validation_report.v1",
        pack_ref=pack.pack_ref,
        program_ref=pack.program.program_ref,
        scope_snapshot_id=pack.scope_snapshot_id,
        field_count=len(pack.candidate.fields),
        evidence_count=len(pack.evidence),
        computed_pack_canonical_sha256=computed_pack,
        computed_semantic_content_sha256=computed_semantic,
        valid=True,
    )


def validate_alpha_program_pack_files(
    *, pack_path: Path, scope_path: Path
) -> AlphaProgramPackValidationReport:
    pack_data = _read_json(pack_path, "program_pack")
    scope_data = _read_json(scope_path, "scope_snapshot")
    try:
        pack = AlphaProgramPackV1.model_validate(pack_data)
    except ValidationError as exc:
        raise AlphaProgramPackValidationError(
            _pydantic_issues("program_pack", exc)
        ) from exc
    try:
        scope = AlphaScopeSnapshotV1.model_validate(scope_data)
    except ValidationError as exc:
        raise AlphaProgramPackValidationError(
            _pydantic_issues("scope_snapshot", exc)
        ) from exc
    return validate_alpha_program_pack(pack=pack, scope=scope)
