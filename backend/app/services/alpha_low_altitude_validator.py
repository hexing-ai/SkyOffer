from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping, Sequence

from backend.app.db.models import EvidenceSupportScope
from backend.app.schemas.alpha_low_altitude import (
    AlphaLowAltitudeIssue,
    AlphaLowAltitudeIssueCode,
    AlphaLowAltitudeValidationReport,
)
from backend.app.schemas.evidence import ReviewedSourceRole
from backend.app.schemas.program_fields import (
    CoverageStatus,
    LowAltitudeBasisFieldV1,
    LowAltitudeInclusionBasis,
    PrimaryDirectionFieldV1,
    ProgramDirection,
    ProgramTaxonomyFieldV1,
    SecondaryDirectionsFieldV1,
)


_CHINESE_CHARACTER = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_COURSE_TYPE_MARKERS = {
    "core": ("core", "compulsory"),
    "required": ("required", "compulsory"),
    "elective": ("elective", "optional"),
}


@dataclass(frozen=True, slots=True)
class AlphaTaxonomyEvidenceView:
    evidence_id: str
    program_ref: str
    excerpt: str
    reviewed_source_role: str | None
    is_v2: bool


@dataclass(frozen=True, slots=True)
class AlphaTaxonomyEvidenceLinkView:
    evidence_id: str
    support_scope: EvidenceSupportScope


@dataclass(frozen=True, slots=True)
class AlphaTaxonomyFieldView:
    field_key: str
    is_critical: bool
    payload: ProgramTaxonomyFieldV1
    evidence_links: tuple[AlphaTaxonomyEvidenceLinkView, ...]


class AlphaLowAltitudeValidationError(ValueError):
    def __init__(self, issues: Sequence[AlphaLowAltitudeIssue]) -> None:
        self.issues = tuple(
            sorted(
                issues,
                key=lambda item: (
                    item.code.value,
                    item.course_name or "",
                    item.evidence_id or "",
                ),
            )
        )
        super().__init__("; ".join(f"{item.code.value}: {item.message}" for item in self.issues))


def _issue(
    code: AlphaLowAltitudeIssueCode,
    message: str,
    *,
    course_name: str | None = None,
    evidence_id: str | None = None,
) -> AlphaLowAltitudeIssue:
    return AlphaLowAltitudeIssue(
        code=code,
        message=message,
        course_name=course_name,
        evidence_id=evidence_id,
    )


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _course_type_supported(course_type: str, excerpt: str) -> bool:
    if course_type == "unknown":
        return True
    normalized = _normalized_text(excerpt)
    return any(
        re.search(rf"\b{re.escape(marker)}\b", normalized)
        for marker in _COURSE_TYPE_MARKERS[course_type]
    )


def validate_low_altitude_taxonomy(
    *,
    program_ref: str,
    fields: Sequence[AlphaTaxonomyFieldView],
    evidence_by_id: Mapping[str, AlphaTaxonomyEvidenceView],
) -> AlphaLowAltitudeValidationReport:
    taxonomy = {field.field_key: field for field in fields}
    primary_field = taxonomy.get("taxonomy.primary_direction")
    secondary_field = taxonomy.get("taxonomy.secondary_directions")
    basis_field = taxonomy.get("taxonomy.low_altitude_basis")

    primary_payload = (
        primary_field.payload
        if primary_field is not None
        and isinstance(primary_field.payload, PrimaryDirectionFieldV1)
        else None
    )
    secondary_payload = (
        secondary_field.payload
        if secondary_field is not None
        and isinstance(secondary_field.payload, SecondaryDirectionsFieldV1)
        else None
    )
    primary = (
        primary_payload.value.direction
        if primary_payload is not None and primary_payload.value is not None
        else None
    )
    secondary = (
        list(secondary_payload.value.directions)
        if secondary_payload is not None and secondary_payload.value is not None
        else []
    )
    applies = ProgramDirection.LOW_ALTITUDE_ECONOMY in ({primary} | set(secondary))
    issues: list[AlphaLowAltitudeIssue] = []

    if applies and basis_field is None:
        issues.append(
            _issue(
                AlphaLowAltitudeIssueCode.BASIS_MISSING,
                "low-altitude direction requires taxonomy.low_altitude_basis",
            )
        )
    if not applies and basis_field is not None:
        issues.append(
            _issue(
                AlphaLowAltitudeIssueCode.BASIS_FORBIDDEN,
                "taxonomy.low_altitude_basis is forbidden without a low-altitude direction",
            )
        )

    basis_payload = (
        basis_field.payload
        if basis_field is not None
        and isinstance(basis_field.payload, LowAltitudeBasisFieldV1)
        else None
    )
    basis = basis_payload.value if basis_payload is not None else None
    if applies and basis_field is not None:
        if not basis_field.is_critical:
            issues.append(
                _issue(
                    AlphaLowAltitudeIssueCode.BASIS_NOT_CRITICAL,
                    "taxonomy.low_altitude_basis must be a critical field",
                )
            )
        if (
            basis_payload is None
            or basis_payload.coverage_status != CoverageStatus.CONFIRMED
        ):
            issues.append(
                _issue(
                    AlphaLowAltitudeIssueCode.BASIS_NOT_CONFIRMED,
                    "manual-review low-altitude basis cannot confirm inclusion",
                )
            )
        if basis is None:
            issues.append(
                _issue(
                    AlphaLowAltitudeIssueCode.BASIS_VALUE_MISSING,
                    "low-altitude basis must contain reviewed course Evidence",
                )
            )

    verified_course_ids: set[str] = set()
    if basis is not None and basis_field is not None:
        if not _CHINESE_CHARACTER.search(basis.rationale_zh):
            issues.append(
                _issue(
                    AlphaLowAltitudeIssueCode.RATIONALE_NOT_CHINESE,
                    "low-altitude inclusion rationale must contain a human-authored Chinese explanation",
                )
            )

        normalized_names = [_normalized_text(course.course_name) for course in basis.courses]
        duplicate_names = sorted(
            {name for name in normalized_names if normalized_names.count(name) > 1}
        )
        for name in duplicate_names:
            issues.append(
                _issue(
                    AlphaLowAltitudeIssueCode.COURSE_NAME_DUPLICATE,
                    "low-altitude qualifying courses must be independent",
                    course_name=name,
                )
            )

        course_subtags = {course.subtag for course in basis.courses}
        for subtag in sorted(set(basis.subtags) - course_subtags, key=lambda item: item.value):
            issues.append(
                _issue(
                    AlphaLowAltitudeIssueCode.SUBTAG_WITHOUT_COURSE,
                    f"declared subtag {subtag.value} lacks qualifying course Evidence",
                )
            )

        link_scope = {
            link.evidence_id: link.support_scope for link in basis_field.evidence_links
        }
        for course in basis.courses:
            evidence = evidence_by_id.get(course.evidence_id)
            if evidence is None:
                issues.append(
                    _issue(
                        AlphaLowAltitudeIssueCode.COURSE_EVIDENCE_MISSING,
                        f"low-altitude course {course.course_name} lacks curriculum Evidence",
                        course_name=course.course_name,
                        evidence_id=course.evidence_id,
                    )
                )
                continue
            course_valid = True
            if evidence.program_ref != program_ref:
                course_valid = False
                issues.append(
                    _issue(
                        AlphaLowAltitudeIssueCode.COURSE_EVIDENCE_PROGRAM_MISMATCH,
                        f"low-altitude course {course.course_name} Evidence belongs to another program",
                        course_name=course.course_name,
                        evidence_id=course.evidence_id,
                    )
                )
            if not evidence.is_v2:
                course_valid = False
                issues.append(
                    _issue(
                        AlphaLowAltitudeIssueCode.COURSE_EVIDENCE_NOT_V2,
                        f"low-altitude course {course.course_name} requires Evidence V2 metadata",
                        course_name=course.course_name,
                        evidence_id=course.evidence_id,
                    )
                )
            if evidence.reviewed_source_role != ReviewedSourceRole.CURRICULUM:
                course_valid = False
                issues.append(
                    _issue(
                        AlphaLowAltitudeIssueCode.COURSE_EVIDENCE_NOT_CURRICULUM,
                        f"low-altitude course {course.course_name} lacks curriculum Evidence",
                        course_name=course.course_name,
                        evidence_id=course.evidence_id,
                    )
                )
            if link_scope.get(course.evidence_id) != EvidenceSupportScope.DIRECT:
                course_valid = False
                issues.append(
                    _issue(
                        AlphaLowAltitudeIssueCode.COURSE_EVIDENCE_NOT_DIRECT,
                        f"low-altitude course {course.course_name} lacks direct Evidence",
                        course_name=course.course_name,
                        evidence_id=course.evidence_id,
                    )
                )
            if _normalized_text(course.course_name) not in _normalized_text(evidence.excerpt):
                course_valid = False
                issues.append(
                    _issue(
                        AlphaLowAltitudeIssueCode.COURSE_NAME_NOT_IN_EXCERPT,
                        f"low-altitude course {course.course_name} is not present in its excerpt",
                        course_name=course.course_name,
                        evidence_id=course.evidence_id,
                    )
                )
            if not _course_type_supported(course.course_type, evidence.excerpt):
                course_valid = False
                issues.append(
                    _issue(
                        AlphaLowAltitudeIssueCode.COURSE_TYPE_NOT_IN_EXCERPT,
                        f"low-altitude course {course.course_name} type is not supported by its excerpt",
                        course_name=course.course_name,
                        evidence_id=course.evidence_id,
                    )
                )
            if course_valid:
                verified_course_ids.add(course.evidence_id)

        if basis.inclusion_basis == LowAltitudeInclusionBasis.EXPLICIT_PROGRAM_FOCUS:
            has_program_focus_evidence = any(
                link.support_scope == EvidenceSupportScope.DIRECT
                and (evidence := evidence_by_id.get(link.evidence_id)) is not None
                and evidence.program_ref == program_ref
                and evidence.is_v2
                and evidence.reviewed_source_role == ReviewedSourceRole.PROGRAM
                for link in basis_field.evidence_links
            )
            if not has_program_focus_evidence:
                issues.append(
                    _issue(
                        AlphaLowAltitudeIssueCode.EXPLICIT_FOCUS_EVIDENCE_MISSING,
                        "explicit_program_focus requires direct official program-name or overview Evidence",
                    )
                )

    if issues:
        raise AlphaLowAltitudeValidationError(issues)

    return AlphaLowAltitudeValidationReport(
        schema_version="alpha_low_altitude_validation_report.v1",
        program_ref=program_ref,
        applies=applies,
        primary_direction=primary,
        secondary_directions=secondary,
        inclusion_basis=basis.inclusion_basis if basis is not None else None,
        declared_subtags=list(basis.subtags) if basis is not None else [],
        course_count=len(basis.courses) if basis is not None else 0,
        verified_course_evidence_ids=sorted(verified_course_ids),
        valid=True,
    )
