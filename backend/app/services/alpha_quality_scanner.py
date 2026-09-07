from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import (
    AuditEvent,
    AuditEventType,
    EvidenceSupportScope,
    Program,
    ProgramPublication,
    ProgramVersion,
    SourceEvidence,
    VersionStatus,
)
from backend.app.repositories.candidates import CandidateRepository
from backend.app.repositories.published_programs import PublishedProgramReader
from backend.app.rules.canonical import content_hash
from backend.app.schemas.alpha_manifest import (
    AlphaManifestProgram,
    AlphaProgramManifestV1,
    AlphaScopeSnapshotV1,
)
from backend.app.schemas.alpha_program_pack import AlphaProgramPackV1
from backend.app.schemas.alpha_quality import (
    AlphaHardGateMetrics,
    AlphaProgramQualityResult,
    AlphaQualityDistributions,
    AlphaQualityMetric,
    AlphaQualityReport,
)
from backend.app.schemas.evidence import (
    belongs_to_official_domains,
    derive_evidence_freshness,
    normalize_aware_utc,
    normalize_official_domain,
)
from backend.app.schemas.field_registry import (
    ProgramFieldRegistry,
    load_program_field_registry,
)
from backend.app.schemas.program_fields import (
    CoverageStatus,
    ProgramDirection,
)
from backend.app.services.alpha_low_altitude_validator import (
    AlphaLowAltitudeValidationError,
    AlphaTaxonomyEvidenceLinkView,
    AlphaTaxonomyEvidenceView,
    AlphaTaxonomyFieldView,
    validate_low_altitude_taxonomy,
)
from backend.app.services.alpha_manifest_validator import (
    program_manifest_hash,
    scope_snapshot_hash,
)
from backend.app.services.alpha_program_pack_validator import (
    AlphaProgramPackValidationError,
    validate_alpha_program_pack,
)


HARD_GATE_NAMES = (
    "scope_compliance_rate",
    "field_inventory_completion_rate",
    "critical_citation_coverage_rate",
    "fresh_evidence_at_publish_rate",
    "four_eye_review_rate",
    "published_only_isolation_rate",
    "low_altitude_evidence_coverage_rate",
    "pack_to_database_semantic_match_rate",
)


class AlphaQualityInputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AlphaQualityScanContext:
    scope: AlphaScopeSnapshotV1
    manifest: AlphaProgramManifestV1
    packs_by_ref: Mapping[str, AlphaProgramPackV1]
    pack_file_sha256_by_ref: Mapping[str, str]
    generated_commit: str
    alembic_revision: str


def _read_json(path: Path, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AlphaQualityInputError(f"{label} file cannot be read") from exc
    except json.JSONDecodeError as exc:
        raise AlphaQualityInputError(f"{label} is not valid JSON") from exc


def load_alpha_quality_context(
    *, root: Path, generated_commit: str, alembic_revision: str
) -> AlphaQualityScanContext:
    try:
        scope = AlphaScopeSnapshotV1.model_validate(
            _read_json(root / "scope_snapshot.json", "scope_snapshot")
        )
        manifest = AlphaProgramManifestV1.model_validate(
            _read_json(root / "manifest.json", "manifest")
        )
    except ValidationError as exc:
        raise AlphaQualityInputError("scope or manifest schema is invalid") from exc
    packs: dict[str, AlphaProgramPackV1] = {}
    pack_file_hashes: dict[str, str] = {}
    for entry in manifest.programs:
        path = (root / entry.pack_path).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise AlphaQualityInputError("pack path escapes the dataset root") from exc
        try:
            raw_bytes = path.read_bytes()
            raw = json.loads(raw_bytes)
            pack = AlphaProgramPackV1.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise AlphaQualityInputError(
                f"Program Pack cannot be loaded: {entry.pack_ref}"
            ) from exc
        packs[entry.pack_ref] = pack
        pack_file_hashes[entry.pack_ref] = hashlib.sha256(raw_bytes).hexdigest()
    return AlphaQualityScanContext(
        scope=scope,
        manifest=manifest,
        packs_by_ref=packs,
        pack_file_sha256_by_ref=pack_file_hashes,
        generated_commit=generated_commit,
        alembic_revision=alembic_revision,
    )


def alpha_quality_input_fingerprint(
    context: AlphaQualityScanContext,
    *,
    registry: ProgramFieldRegistry | None = None,
) -> str:
    registry = registry or load_program_field_registry()
    return content_hash(
        {
            "generated_commit": context.generated_commit,
            "alembic_revision": context.alembic_revision,
            "registry_sha256": content_hash(registry),
            "scope_sha256": scope_snapshot_hash(context.scope),
            "manifest_sha256": program_manifest_hash(context.manifest),
            "packs": [
                {
                    "pack_ref": pack_ref,
                    "pack_canonical_sha256": pack.pack_canonical_sha256,
                    "expected_semantic_content_sha256": (
                        pack.expected_semantic_content_sha256
                    ),
                    "pack_model_sha256": content_hash(pack),
                    "file_sha256": context.pack_file_sha256_by_ref.get(pack_ref),
                }
                for pack_ref, pack in sorted(context.packs_by_ref.items())
            ],
        }
    )


def alpha_quality_report_is_current(
    report: AlphaQualityReport,
    context: AlphaQualityScanContext,
    *,
    registry: ProgramFieldRegistry | None = None,
) -> bool:
    return report.input_fingerprint_sha256 == alpha_quality_input_fingerprint(
        context, registry=registry
    )


def _metric(numerator: int, denominator: int) -> AlphaQualityMetric:
    rate = Decimal(numerator) / Decimal(denominator) if denominator else Decimal(0)
    return AlphaQualityMetric(
        numerator=numerator,
        denominator=denominator,
        rate=rate,
        passed=rate == Decimal(1),
    )


def _pack_directions(
    pack: AlphaProgramPackV1,
) -> tuple[ProgramDirection | None, set[ProgramDirection]]:
    fields = {field.field_key: field for field in pack.candidate.fields}
    primary_field = fields.get("taxonomy.primary_direction")
    secondary_field = fields.get("taxonomy.secondary_directions")
    primary = (
        primary_field.value_payload.value.direction
        if primary_field is not None and primary_field.value_payload.value is not None
        else None
    )
    secondary = (
        set(secondary_field.value_payload.value.directions)
        if secondary_field is not None
        and secondary_field.value_payload.value is not None
        else set()
    )
    return primary, secondary


def _expected_field_keys(
    entry: AlphaManifestProgram, registry: ProgramFieldRegistry
) -> set[str]:
    result = {
        definition.field_key
        for definition in registry.fields
        if definition.presence == "required"
    }
    directions = {entry.primary_direction, *entry.secondary_directions}
    if ProgramDirection.LOW_ALTITUDE_ECONOMY in directions:
        result.add("taxonomy.low_altitude_basis")
    return result


def _required_support_scope(coverage: CoverageStatus | None) -> EvidenceSupportScope:
    if coverage == CoverageStatus.NOT_FOUND_IN_REVIEWED_SOURCES:
        return EvidenceSupportScope.COVERAGE
    if coverage == CoverageStatus.NOT_APPLICABLE:
        return EvidenceSupportScope.APPLICABILITY
    return EvidenceSupportScope.DIRECT


def _evidence_is_official(
    evidence: SourceEvidence | None, *, program: Program
) -> bool:
    if evidence is None or evidence.program_id != program.id:
        return False
    if any(
        value is None
        for value in (
            evidence.capture_method,
            evidence.hash_scope,
            evidence.reviewed_source_role,
        )
    ):
        return False
    try:
        host = normalize_official_domain(urlsplit(evidence.url).hostname or "")
        return belongs_to_official_domains(
            host,
            registered_domain=program.registered_official_domain,
            aliases=program.official_domain_aliases,
        )
    except ValueError:
        return False


class AlphaQualityScanner:
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

    def scan(self, context: AlphaQualityScanContext) -> AlphaQualityReport:
        now = normalize_aware_utc(self._clock())
        scope_hash = scope_snapshot_hash(context.scope)
        manifest_hash = program_manifest_hash(context.manifest)
        registry_hash = content_hash(self._registry)
        structural_issues = self._structural_issues(
            context, scope_hash=scope_hash, manifest_hash=manifest_hash
        )

        results: list[AlphaProgramQualityResult] = []
        inventory_numerator = 0
        inventory_denominator = 0
        citation_numerator = 0
        citation_denominator = 0
        scope_numerator = 0
        fresh_numerator = 0
        four_eye_numerator = 0
        isolation_numerator = 0
        semantic_numerator = 0
        low_altitude_numerator = 0
        low_altitude_denominator = 0
        published_count = 0
        region_counts: Counter[str] = Counter()
        institution_counts: Counter[str] = Counter()
        primary_counts: Counter[str] = Counter()
        secondary_counts: Counter[str] = Counter()
        coverage_counts: Counter[str] = Counter()
        review_durations: dict[str, int] = {}

        for entry in context.manifest.programs:
            pack = context.packs_by_ref.get(entry.pack_ref)
            result, actual_coverages = self._scan_program(
                context=context,
                entry=entry,
                pack=pack,
                now=now,
            )
            results.append(result)
            inventory_numerator += result.present_field_count
            inventory_denominator += result.expected_field_count
            citation_numerator += result.qualified_critical_field_count
            citation_denominator += result.expected_critical_field_count
            scope_numerator += int(result.scope_compliant)
            fresh_numerator += int(result.fresh_at_publish)
            four_eye_numerator += int(result.four_eye_reviewed)
            isolation_numerator += int(result.published_only_isolated)
            semantic_numerator += int(result.pack_database_semantic_match)
            is_low_altitude = ProgramDirection.LOW_ALTITUDE_ECONOMY in {
                entry.primary_direction,
                *entry.secondary_directions,
            }
            if is_low_altitude:
                low_altitude_denominator += 1
                low_altitude_numerator += int(
                    result.low_altitude_evidence_complete
                )
            if result.published_version_id is not None:
                published_count += 1
                region_counts[entry.region.value] += 1
                institution_counts[entry.institution_ref] += 1
                primary_counts[entry.primary_direction.value] += 1
                secondary_counts.update(
                    direction.value for direction in entry.secondary_directions
                )
            coverage_counts.update(actual_coverages)
            version = (
                self._session.get(ProgramVersion, result.published_version_id)
                if result.published_version_id is not None
                else None
            )
            if (
                version is not None
                and version.submitted_at is not None
                and version.reviewed_at is not None
                and version.reviewed_at >= version.submitted_at
            ):
                review_durations[entry.program_ref] = int(
                    (version.reviewed_at - version.submitted_at).total_seconds()
                )

        expected_programs = len(context.manifest.programs)
        low_altitude_metric = (
            _metric(low_altitude_numerator, low_altitude_denominator)
            if low_altitude_denominator
            else _metric(0, 0)
        )
        hard_gates = AlphaHardGateMetrics(
            scope_compliance_rate=_metric(scope_numerator, expected_programs),
            field_inventory_completion_rate=_metric(
                inventory_numerator, inventory_denominator
            ),
            critical_citation_coverage_rate=_metric(
                citation_numerator, citation_denominator
            ),
            fresh_evidence_at_publish_rate=_metric(
                fresh_numerator, expected_programs
            ),
            four_eye_review_rate=_metric(four_eye_numerator, expected_programs),
            published_only_isolation_rate=_metric(
                isolation_numerator, expected_programs
            ),
            low_altitude_evidence_coverage_rate=low_altitude_metric,
            pack_to_database_semantic_match_rate=_metric(
                semantic_numerator, expected_programs
            ),
        )
        blocking_gates = [
            name
            for name in HARD_GATE_NAMES
            if not getattr(hard_gates, name).passed
        ]
        if structural_issues:
            blocking_gates.append("structural_contract")
        return AlphaQualityReport(
            schema_version="alpha_quality_report.v1",
            dataset_id=context.manifest.dataset_id,
            generated_at=now,
            generated_commit=context.generated_commit,
            alembic_revision=context.alembic_revision,
            registry_schema_version=self._registry.schema_version,
            registry_version=self._registry.registry_version,
            registry_sha256=registry_hash,
            scope_schema_version=context.scope.schema_version,
            scope_snapshot_id=context.scope.snapshot_id,
            scope_sha256=scope_hash,
            manifest_schema_version=context.manifest.schema_version,
            manifest_sha256=manifest_hash,
            pack_canonical_sha256_by_ref={
                ref: pack.pack_canonical_sha256
                for ref, pack in context.packs_by_ref.items()
            },
            input_fingerprint_sha256=alpha_quality_input_fingerprint(
                context, registry=self._registry
            ),
            published_program_count=published_count,
            hard_gates=hard_gates,
            blocking_gates=blocking_gates,
            ready=not blocking_gates,
            distributions=AlphaQualityDistributions(
                region_counts=dict(sorted(region_counts.items())),
                institution_counts=dict(sorted(institution_counts.items())),
                primary_direction_counts=dict(sorted(primary_counts.items())),
                secondary_direction_counts=dict(sorted(secondary_counts.items())),
                coverage_status_counts=dict(sorted(coverage_counts.items())),
                review_duration_seconds_by_program=dict(sorted(review_durations.items())),
            ),
            programs=results,
            structural_issues=structural_issues,
        )

    def _structural_issues(
        self,
        context: AlphaQualityScanContext,
        *,
        scope_hash: str,
        manifest_hash: str,
    ) -> list[str]:
        issues: list[str] = []
        if context.scope.template_state != "frozen_reviewed" or not context.scope.publishable:
            issues.append("scope snapshot is not frozen and publishable")
        if context.scope.canonical_sha256 != scope_hash:
            issues.append("scope canonical hash mismatch")
        if (
            context.manifest.template_state != "frozen_reviewed"
            or not context.manifest.publishable
        ):
            issues.append("manifest is not frozen and publishable")
        if context.manifest.manifest_sha256 != manifest_hash:
            issues.append("manifest canonical hash mismatch")
        if context.manifest.scope_snapshot_id != context.scope.snapshot_id:
            issues.append("manifest scope ref mismatch")
        if (
            context.manifest.field_registry.schema_version
            != self._registry.schema_version
            or context.manifest.field_registry.registry_version
            != self._registry.registry_version
        ):
            issues.append("manifest Registry ref mismatch")
        manifest_refs = {entry.pack_ref for entry in context.manifest.programs}
        if set(context.packs_by_ref) != manifest_refs:
            issues.append("manifest and loaded Pack refs differ")
        if set(context.pack_file_sha256_by_ref) != manifest_refs:
            issues.append("manifest and loaded Pack file hashes differ")
        for entry in context.manifest.programs:
            if context.pack_file_sha256_by_ref.get(entry.pack_ref) != entry.pack_sha256:
                issues.append(f"pack file hash mismatch: {entry.pack_ref}")
        publication_program_ids = set(
            self._session.scalars(select(ProgramPublication.program_id)).all()
        )
        manifest_program_ids = {entry.program_ref for entry in context.manifest.programs}
        extras = sorted(publication_program_ids - manifest_program_ids)
        if extras:
            issues.append("published Programs exist outside the frozen manifest")
        return sorted(set(issues))

    def _scan_program(
        self,
        *,
        context: AlphaQualityScanContext,
        entry: AlphaManifestProgram,
        pack: AlphaProgramPackV1 | None,
        now: datetime,
    ) -> tuple[AlphaProgramQualityResult, list[str]]:
        issues: list[str] = []
        expected_keys = _expected_field_keys(entry, self._registry)
        critical_keys = {
            key
            for key in expected_keys
            if self._registry.definition_for(key).is_critical
        }
        scope_compliant = False
        if pack is None:
            issues.append("Program Pack is missing")
        else:
            try:
                validate_alpha_program_pack(pack=pack, scope=context.scope)
                primary, secondary = _pack_directions(pack)
                entry_matches = (
                    pack.pack_ref == entry.pack_ref
                    and pack.program.program_ref == entry.program_ref
                    and pack.scope_institution_ref == entry.institution_ref
                    and pack.program.region == entry.region
                    and pack.program.degree_type == entry.degree_type
                    and primary == entry.primary_direction
                    and secondary == set(entry.secondary_directions)
                )
                if not entry_matches:
                    issues.append("Pack identity differs from its manifest entry")
            except AlphaProgramPackValidationError:
                entry_matches = False
                issues.append("Program Pack validator failed")

        program = self._session.get(Program, entry.program_ref)
        if program is None:
            issues.append("database Program is missing")
        elif pack is not None:
            program_matches = (
                program.official_name == pack.program.official_name
                and program.institution_name == pack.program.institution_name
                and str(program.region) == pack.program.region.value
                and program.official_program_url == pack.program.official_program_url
                and program.registered_official_domain
                == pack.program.registered_official_domain
                and program.official_domain_aliases
                == pack.program.official_domain_aliases
            )
            scope_compliant = entry_matches and program_matches
            if not program_matches:
                issues.append("database Program identity differs from Pack")

        publication = self._session.get(ProgramPublication, entry.program_ref)
        version = (
            self._session.get(ProgramVersion, publication.current_version_id)
            if publication is not None
            else None
        )
        valid_published = False
        if publication is None or version is None:
            issues.append("current published version is missing")
        elif (
            version.program_id != entry.program_ref
            or version.status != VersionStatus.PUBLISHED
            or version.published_at is None
        ):
            issues.append("publication pointer is invalid")
        else:
            valid_published = True

        candidate = None
        if version is not None:
            try:
                candidate = CandidateRepository(
                    self._session,
                    clock=self._clock,
                    id_factory=lambda _kind: "unused.quality.scan",
                ).get(version.id)
            except (ValidationError, KeyError, ValueError):
                issues.append("published candidate payload cannot be parsed")
        field_by_key = (
            {field.field_key: field for field in candidate.fields}
            if candidate is not None
            else {}
        )
        present_count = len(expected_keys & set(field_by_key))
        if present_count != len(expected_keys):
            issues.append("mandatory field inventory is incomplete")

        evidence_ids = sorted(
            {
                link.evidence_id
                for field in field_by_key.values()
                for link in field.evidence_links
            }
        )
        evidence = {
            record.id: record
            for record in self._session.scalars(
                select(SourceEvidence).where(SourceEvidence.id.in_(evidence_ids))
            ).all()
        }
        qualified_critical = 0
        coverages: list[str] = []
        for field_key, field in field_by_key.items():
            coverage = getattr(field.value_payload, "coverage_status", None)
            if coverage is not None:
                coverages.append(coverage.value)
            if field_key not in critical_keys or program is None:
                continue
            required_scope = _required_support_scope(coverage)
            if any(
                link.support_scope == required_scope
                and _evidence_is_official(evidence.get(link.evidence_id), program=program)
                for link in field.evidence_links
            ):
                qualified_critical += 1
        if qualified_critical != len(critical_keys):
            issues.append("critical citation coverage is incomplete")

        fresh_at_publish = False
        if version is not None and version.published_at is not None and evidence_ids:
            fresh_at_publish = len(evidence) == len(evidence_ids) and all(
                derive_evidence_freshness(
                    availability=record.availability_at_verification,
                    review_due_at=record.review_due_at,
                    expires_at=record.expires_at,
                    now=version.published_at,
                ).value
                == "fresh"
                for record in evidence.values()
            )
        if not fresh_at_publish:
            issues.append("supporting Evidence was not fresh at publish time")

        four_eye = self._four_eye(version)
        if not four_eye:
            issues.append("four-eye review metadata or Audit is incomplete")

        isolated = False
        if program is not None and publication is not None and version is not None:
            try:
                public = PublishedProgramReader(
                    self._session, clock=lambda: now
                ).get(program.id)
                other_published = self._session.scalars(
                    select(ProgramVersion.id).where(
                        ProgramVersion.program_id == program.id,
                        ProgramVersion.status == VersionStatus.PUBLISHED,
                        ProgramVersion.id != publication.current_version_id,
                    )
                ).all()
                isolated = (
                    public.version_id == publication.current_version_id
                    and not other_published
                )
            except Exception:
                isolated = False
        if not isolated:
            issues.append("published-only isolation check failed")

        is_low_altitude = ProgramDirection.LOW_ALTITUDE_ECONOMY in {
            entry.primary_direction,
            *entry.secondary_directions,
        }
        low_altitude_complete = not is_low_altitude or self._low_altitude_complete(
            program_ref=entry.program_ref,
            field_by_key=field_by_key,
            evidence=evidence,
        )
        if not low_altitude_complete:
            issues.append("low-altitude course Evidence is incomplete")

        semantic_match = False
        if version is not None and pack is not None:
            semantic_match = (
                version.content_sha256 == pack.expected_semantic_content_sha256
                and CandidateRepository(
                    self._session,
                    clock=self._clock,
                    id_factory=lambda _kind: "unused.quality.hash",
                ).content_hash_is_valid(version.id)
            )
        if not semantic_match:
            issues.append("Pack and database semantic hashes differ")

        return (
            AlphaProgramQualityResult(
                pack_ref=entry.pack_ref,
                program_ref=entry.program_ref,
                published_version_id=version.id if valid_published else None,
                scope_compliant=scope_compliant,
                expected_field_count=len(expected_keys),
                present_field_count=present_count,
                expected_critical_field_count=len(critical_keys),
                qualified_critical_field_count=qualified_critical,
                fresh_at_publish=fresh_at_publish,
                four_eye_reviewed=four_eye,
                published_only_isolated=isolated,
                low_altitude_evidence_complete=low_altitude_complete,
                pack_database_semantic_match=semantic_match,
                issues=issues,
            ),
            coverages,
        )

    def _four_eye(self, version: ProgramVersion | None) -> bool:
        if (
            version is None
            or not version.submitted_by
            or not version.reviewed_by
            or version.submitted_by == version.reviewed_by
            or not version.review_note
            or version.submitted_at is None
            or version.reviewed_at is None
            or version.reviewed_at < version.submitted_at
        ):
            return False
        audits = self._session.scalars(
            select(AuditEvent).where(AuditEvent.version_id == version.id)
        ).all()
        submit = [item for item in audits if item.event_type == AuditEventType.SUBMIT]
        publish = [item for item in audits if item.event_type == AuditEventType.PUBLISH]
        return (
            len(submit) == 1
            and len(publish) == 1
            and submit[0].actor_ref == version.submitted_by
            and publish[0].actor_ref == version.reviewed_by
            and bool(submit[0].request_id)
            and bool(publish[0].request_id)
        )

    @staticmethod
    def _low_altitude_complete(
        *,
        program_ref: str,
        field_by_key: Mapping[str, object],
        evidence: Mapping[str, SourceEvidence],
    ) -> bool:
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
            for field in field_by_key.values()
            if field.value_schema_version == "program_taxonomy_field.v1"
        ]
        evidence_views = {
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
            report = validate_low_altitude_taxonomy(
                program_ref=program_ref,
                fields=taxonomy_fields,
                evidence_by_id=evidence_views,
            )
        except AlphaLowAltitudeValidationError:
            return False
        return report.applies
