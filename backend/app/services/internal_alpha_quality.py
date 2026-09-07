from __future__ import annotations

import hashlib
import json
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
    EvidenceAvailability,
    Program,
    ProgramPublication,
    ProgramVersion,
    SourceEvidence,
    VersionStatus,
)
from backend.app.repositories.candidates import CandidateRepository
from backend.app.rules.canonical import content_hash
from backend.app.schemas.alpha_manifest import AlphaScopeSnapshotV1
from backend.app.schemas.alpha_program_pack import AlphaProgramPackV1
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
from backend.app.schemas.internal_alpha import (
    InternalAlphaManifestV1,
    InternalAlphaProgram,
    InternalAlphaProgramQualityResult,
    InternalAlphaQualityGates,
    InternalAlphaQualityMetric,
    InternalAlphaQualityReport,
)
from backend.app.schemas.program_fields import CoverageStatus, ProgramDirection
from backend.app.services.alpha_manifest_validator import scope_snapshot_hash
from backend.app.services.alpha_program_pack_validator import (
    AlphaProgramPackValidationError,
    validate_alpha_program_pack,
)


GATE_NAMES = (
    "manifest_integrity",
    "pack_contract",
    "field_inventory",
    "official_fresh_evidence",
    "candidate_database_match",
    "candidate_only_isolation",
    "risk_and_exception_disclosure",
)


class InternalAlphaQualityInputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class InternalAlphaQualityContext:
    root: Path
    scope: AlphaScopeSnapshotV1
    manifest: InternalAlphaManifestV1
    packs_by_ref: Mapping[str, AlphaProgramPackV1]
    pack_file_sha256_by_ref: Mapping[str, str]
    generated_commit: str


def internal_alpha_manifest_hash(manifest: InternalAlphaManifestV1) -> str:
    return content_hash(
        manifest.model_dump(mode="python", exclude={"manifest_sha256"})
    )


def _read_json(path: Path, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InternalAlphaQualityInputError(f"{label} cannot be read") from exc
    except json.JSONDecodeError as exc:
        raise InternalAlphaQualityInputError(f"{label} is not valid JSON") from exc


def load_internal_alpha_quality_context(
    *, root: Path, generated_commit: str
) -> InternalAlphaQualityContext:
    try:
        scope = AlphaScopeSnapshotV1.model_validate(
            _read_json(root / "scope_snapshot.json", "scope snapshot")
        )
        manifest = InternalAlphaManifestV1.model_validate(
            _read_json(root / "internal_manifest.json", "internal manifest")
        )
    except ValidationError as exc:
        raise InternalAlphaQualityInputError(
            "internal Alpha context schema is invalid"
        ) from exc

    packs: dict[str, AlphaProgramPackV1] = {}
    file_hashes: dict[str, str] = {}
    root_resolved = root.resolve()
    for entry in manifest.programs:
        path = (root / entry.pack_path).resolve()
        try:
            path.relative_to(root_resolved)
        except ValueError as exc:
            raise InternalAlphaQualityInputError(
                f"pack path escapes dataset root: {entry.pack_ref}"
            ) from exc
        try:
            raw_bytes = path.read_bytes()
            pack = AlphaProgramPackV1.model_validate(json.loads(raw_bytes))
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise InternalAlphaQualityInputError(
                f"Program Pack cannot be loaded: {entry.pack_ref}"
            ) from exc
        if pack.pack_ref in packs:
            raise InternalAlphaQualityInputError("duplicate Pack ref")
        packs[pack.pack_ref] = pack
        file_hashes[pack.pack_ref] = hashlib.sha256(raw_bytes).hexdigest()
    return InternalAlphaQualityContext(
        root=root,
        scope=scope,
        manifest=manifest,
        packs_by_ref=packs,
        pack_file_sha256_by_ref=file_hashes,
        generated_commit=generated_commit,
    )


def internal_alpha_input_fingerprint(
    context: InternalAlphaQualityContext,
    *, registry: ProgramFieldRegistry | None = None,
) -> str:
    registry = registry or load_program_field_registry()
    return content_hash(
        {
            "generated_commit": context.generated_commit,
            "manifest_sha256": internal_alpha_manifest_hash(context.manifest),
            "scope_sha256": scope_snapshot_hash(context.scope),
            "registry_sha256": content_hash(registry),
            "pack_file_sha256_by_ref": dict(
                sorted(context.pack_file_sha256_by_ref.items())
            ),
        }
    )


def _metric(numerator: int, denominator: int) -> InternalAlphaQualityMetric:
    rate = Decimal(numerator) / Decimal(denominator) if denominator else Decimal(0)
    return InternalAlphaQualityMetric(
        numerator=numerator,
        denominator=denominator,
        rate=rate,
        passed=rate == Decimal(1),
    )


def _expected_field_keys(
    pack: AlphaProgramPackV1, registry: ProgramFieldRegistry
) -> set[str]:
    result = {
        item.field_key for item in registry.fields if item.presence == "required"
    }
    directions: set[ProgramDirection] = set()
    for field in pack.candidate.fields:
        if field.field_key == "taxonomy.primary_direction":
            directions.add(field.value_payload.value.direction)
        elif field.field_key == "taxonomy.secondary_directions":
            directions.update(field.value_payload.value.directions)
    if ProgramDirection.LOW_ALTITUDE_ECONOMY in directions:
        result.add("taxonomy.low_altitude_basis")
    return result


def _evidence_is_official_and_fresh(
    evidence,
    *, pack: AlphaProgramPackV1,
    now: datetime,
) -> bool:
    try:
        host = normalize_official_domain(urlsplit(evidence.url).hostname or "")
    except ValueError:
        return False
    return (
        evidence.program_id == pack.program.program_ref
        and evidence.availability_at_verification == EvidenceAvailability.AVAILABLE
        and belongs_to_official_domains(
            host,
            registered_domain=pack.program.registered_official_domain,
            aliases=pack.program.official_domain_aliases,
        )
        and derive_evidence_freshness(
            availability=evidence.availability_at_verification,
            review_due_at=evidence.review_due_at,
            expires_at=evidence.expires_at,
            now=now,
        ).value
        == "fresh"
    )


class InternalAlphaQualityScanner:
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

    def scan(self, context: InternalAlphaQualityContext) -> InternalAlphaQualityReport:
        now = normalize_aware_utc(self._clock())
        manifest_hash = internal_alpha_manifest_hash(context.manifest)
        structural_issues = self._structural_issues(context, manifest_hash)

        totals = {name: 0 for name in GATE_NAMES}
        denominator = len(context.manifest.programs)
        results: list[InternalAlphaProgramQualityResult] = []
        for entry in context.manifest.programs:
            result, passed_gates = self._scan_program(context, entry, now)
            results.append(result)
            for gate in passed_gates:
                totals[gate] += 1

        gates = InternalAlphaQualityGates(
            **{name: _metric(totals[name], denominator) for name in GATE_NAMES}
        )
        blocking = [
            name for name in GATE_NAMES if not getattr(gates, name).passed
        ]
        if structural_issues:
            blocking.append("structural_contract")
        return InternalAlphaQualityReport(
            schema_version="internal_alpha_quality_report.v1",
            dataset_id=context.manifest.dataset_id,
            generated_at=now,
            generated_commit=context.generated_commit,
            manifest_sha256=manifest_hash,
            input_fingerprint_sha256=internal_alpha_input_fingerprint(
                context, registry=self._registry
            ),
            program_count=denominator,
            gates=gates,
            blocking_gates=blocking,
            ready_for_internal_mvp=not blocking,
            programs=results,
            structural_issues=structural_issues,
        )

    def _structural_issues(
        self, context: InternalAlphaQualityContext, manifest_hash: str
    ) -> list[str]:
        issues: list[str] = []
        manifest = context.manifest
        if manifest.manifest_sha256 != manifest_hash:
            issues.append("internal manifest canonical hash mismatch")
        if manifest.source_scope_snapshot_id != context.scope.snapshot_id:
            issues.append("internal manifest scope snapshot mismatch")
        if context.scope.canonical_sha256 != scope_snapshot_hash(context.scope):
            issues.append("scope snapshot canonical hash mismatch")
        if manifest.target_academic_year != context.scope.target_academic_year:
            issues.append("internal manifest target academic year mismatch")
        if (
            manifest.field_registry_schema_version != self._registry.schema_version
            or manifest.field_registry_version != self._registry.registry_version
        ):
            issues.append("internal manifest Registry reference mismatch")
        refs = {entry.pack_ref for entry in manifest.programs}
        if refs != set(context.packs_by_ref):
            issues.append("internal manifest and loaded Pack refs differ")
        if refs != set(context.pack_file_sha256_by_ref):
            issues.append("internal manifest and loaded Pack file hashes differ")
        return sorted(set(issues))

    def _scan_program(
        self,
        context: InternalAlphaQualityContext,
        entry: InternalAlphaProgram,
        now: datetime,
    ) -> tuple[InternalAlphaProgramQualityResult, set[str]]:
        issues: list[str] = []
        passed: set[str] = set()
        pack = context.packs_by_ref.get(entry.pack_ref)
        if pack is None:
            return (
                InternalAlphaProgramQualityResult(
                    pack_ref=entry.pack_ref,
                    program_ref=entry.program_ref,
                    candidate_version_id=entry.candidate_version_id,
                    field_count=0,
                    evidence_count=0,
                    high_risk_field_keys=[],
                    exception_field_keys=[],
                    passed=False,
                    issues=["Program Pack is missing"],
                ),
                passed,
            )

        identity_matches = (
            pack.program.program_ref == entry.program_ref
            and pack.scope_institution_ref == entry.institution_ref
            and pack.program.region == entry.region
            and pack.pack_canonical_sha256 == entry.pack_canonical_sha256
            and pack.expected_semantic_content_sha256
            == entry.candidate_semantic_sha256
            and context.pack_file_sha256_by_ref.get(entry.pack_ref)
            == entry.pack_file_sha256
        )
        if identity_matches:
            passed.add("manifest_integrity")
        else:
            issues.append("Pack identity or hash differs from internal manifest")

        try:
            validate_alpha_program_pack(
                pack=pack, scope=context.scope, registry=self._registry
            )
            passed.add("pack_contract")
        except AlphaProgramPackValidationError:
            issues.append("Program Pack contract validation failed")

        expected_keys = _expected_field_keys(pack, self._registry)
        field_by_key = {field.field_key: field for field in pack.candidate.fields}
        if set(field_by_key) == expected_keys:
            passed.add("field_inventory")
        else:
            issues.append("mandatory field inventory differs from Registry")

        if pack.evidence and all(
            _evidence_is_official_and_fresh(item, pack=pack, now=now)
            for item in pack.evidence
        ):
            passed.add("official_fresh_evidence")
        else:
            issues.append("Evidence is unofficial, unavailable, due, or expired")

        exception_fields: list[str] = []
        high_risk_fields: list[str] = []
        disclosure_ok = True
        for field in pack.candidate.fields:
            coverage = getattr(field.value_payload, "coverage_status", None)
            if coverage is None or coverage == CoverageStatus.CONFIRMED:
                continue
            exception_fields.append(field.field_key)
            if field.is_critical:
                high_risk_fields.append(field.field_key)
            reason = getattr(field.value_payload, "reason", None)
            reviewed_ids = getattr(field.value_payload, "reviewed_source_ids", [])
            if reason is None or not reviewed_ids:
                disclosure_ok = False
        if disclosure_ok:
            passed.add("risk_and_exception_disclosure")
        else:
            issues.append("risk or exception field is not explicitly disclosed")

        database_matches = self._database_matches(entry, pack)
        if database_matches:
            passed.add("candidate_database_match")
        else:
            issues.append("database Candidate does not match frozen Pack")

        publication = self._session.get(ProgramPublication, entry.program_ref)
        version = self._session.get(ProgramVersion, entry.candidate_version_id)
        isolated = (
            publication is None
            and version is not None
            and version.status == VersionStatus.CANDIDATE
            and version.submitted_at is None
            and version.reviewed_at is None
            and version.published_at is None
        )
        if isolated:
            passed.add("candidate_only_isolation")
        else:
            issues.append("Candidate-only publication boundary was violated")

        return (
            InternalAlphaProgramQualityResult(
                pack_ref=entry.pack_ref,
                program_ref=entry.program_ref,
                candidate_version_id=entry.candidate_version_id,
                field_count=len(pack.candidate.fields),
                evidence_count=len(pack.evidence),
                high_risk_field_keys=high_risk_fields,
                exception_field_keys=exception_fields,
                passed=not issues,
                issues=issues,
            ),
            passed,
        )

    def _database_matches(
        self, entry: InternalAlphaProgram, pack: AlphaProgramPackV1
    ) -> bool:
        program = self._session.get(Program, entry.program_ref)
        version = self._session.get(ProgramVersion, entry.candidate_version_id)
        if program is None or version is None:
            return False
        if (
            version.program_id != entry.program_ref
            or version.content_sha256 != entry.candidate_semantic_sha256
            or version.status != VersionStatus.CANDIDATE
        ):
            return False
        if (
            program.official_name != pack.program.official_name
            or program.institution_name != pack.program.institution_name
            or program.official_program_url != pack.program.official_program_url
        ):
            return False
        try:
            candidate = CandidateRepository(
                self._session,
                clock=self._clock,
                id_factory=lambda _kind: "unused.internal.alpha.scan",
            ).get(version.id)
        except (KeyError, ValidationError, ValueError):
            return False
        if candidate.content_sha256 != pack.expected_semantic_content_sha256:
            return False
        evidence_by_id = {
            item.id: item
            for item in self._session.scalars(
                select(SourceEvidence).where(
                    SourceEvidence.id.in_([value.id for value in pack.evidence])
                )
            ).all()
        }
        if set(evidence_by_id) != {item.id for item in pack.evidence}:
            return False
        return all(
            evidence_by_id[item.id].program_id == entry.program_ref
            and evidence_by_id[item.id].snapshot_sha256 == item.snapshot_sha256
            for item in pack.evidence
        )
