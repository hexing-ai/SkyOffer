from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from backend.app.rules.canonical import content_hash
from backend.app.schemas.alpha_manifest import (
    AlphaProgramManifestV1,
    AlphaScopeSnapshotV1,
)
from backend.app.schemas.field_registry import ProgramFieldRegistry
from backend.app.schemas.profile_analysis import StrictModel
from backend.app.schemas.evidence import Sha256Hex


class AlphaManifestValidationError(ValueError):
    def __init__(self, issues: list[str]) -> None:
        self.issues = tuple(sorted(set(issues)))
        super().__init__("; ".join(self.issues))


class AlphaManifestValidationReport(StrictModel):
    schema_version: Literal["alpha_manifest_validation_report.v1"]
    dataset_id: str
    scope_snapshot_id: str | None
    computed_scope_sha256: Sha256Hex
    stored_scope_hash_matches: bool | None
    computed_manifest_sha256: Sha256Hex
    stored_manifest_hash_matches: bool | None
    checked_pack_count: Annotated[int, Field(ge=0, le=30)]
    publishable: bool
    blocking_reasons: list[str]


def _pydantic_issues(label: str, exc: ValidationError) -> list[str]:
    return [
        f"{label}.{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors()
    ]


def _read_json(path: Path, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AlphaManifestValidationError([f"{label} file cannot be read"]) from exc
    except json.JSONDecodeError as exc:
        raise AlphaManifestValidationError([f"{label} is not valid JSON"]) from exc


def scope_snapshot_hash(snapshot: AlphaScopeSnapshotV1) -> str:
    return content_hash(
        snapshot.model_dump(mode="python", exclude={"canonical_sha256"})
    )


def program_manifest_hash(manifest: AlphaProgramManifestV1) -> str:
    return content_hash(
        manifest.model_dump(mode="python", exclude={"manifest_sha256"})
    )


def _byte_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_file(root: Path, relative_path: str) -> Path:
    candidate = root / relative_path
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    if resolved_candidate.parent != (resolved_root / "programs"):
        raise AlphaManifestValidationError(
            [f"pack path escapes the programs directory: {relative_path}"]
        )
    if candidate.is_symlink() or not candidate.is_file():
        raise AlphaManifestValidationError(
            [f"pack file is missing or not a regular file: {relative_path}"]
        )
    return candidate


def _validate_registry(root: Path, manifest: AlphaProgramManifestV1) -> list[str]:
    issues: list[str] = []
    registry_path = root / manifest.field_registry.path
    if registry_path.is_symlink() or not registry_path.is_file():
        return ["field registry file is missing or not a regular file"]
    try:
        registry = ProgramFieldRegistry.model_validate(
            json.loads(registry_path.read_text(encoding="utf-8"))
        )
    except OSError:
        return ["field registry file cannot be read"]
    except json.JSONDecodeError:
        return ["field registry is not valid JSON"]
    except ValidationError as exc:
        return _pydantic_issues("field_registry", exc)
    if registry.schema_version != manifest.field_registry.schema_version:
        issues.append("manifest field registry schema version does not match file")
    if registry.registry_version != manifest.field_registry.registry_version:
        issues.append("manifest field registry version does not match file")
    return issues


def validate_alpha_manifest(
    *,
    scope: AlphaScopeSnapshotV1,
    manifest: AlphaProgramManifestV1,
    root: Path | None,
    require_publishable: bool = False,
) -> AlphaManifestValidationReport:
    issues: list[str] = []
    if scope.target_academic_year != manifest.target_academic_year:
        issues.append("scope and manifest target academic years do not match")
    if manifest.scope_snapshot_id != scope.snapshot_id:
        issues.append("manifest scope_snapshot_id does not match scope snapshot_id")
    if (
        scope.reviewed_by is not None
        and scope.reviewed_by != manifest.review_plan.domain_reviewer
    ):
        issues.append("scope reviewer does not match the approved domain reviewer")
    if (
        manifest.frozen_by is not None
        and manifest.frozen_by != manifest.review_plan.domain_reviewer
    ):
        issues.append("manifest freezer does not match the approved domain reviewer")
    if (
        scope.reviewed_at is not None
        and manifest.frozen_at is not None
        and manifest.frozen_at < scope.reviewed_at
    ):
        issues.append("manifest frozen_at cannot be before scope reviewed_at")

    scope_entries = {
        item.institution_ref: item
        for item in (
            *scope.hong_kong_eight.institutions,
            *scope.united_kingdom_qs_top_100.institutions,
        )
    }
    for program in manifest.programs:
        institution = scope_entries.get(program.institution_ref)
        if institution is None:
            issues.append(
                f"program {program.program_ref} references an institution outside scope"
            )
        elif institution.region != program.region:
            issues.append(
                f"program {program.program_ref} region does not match its scope entry"
            )

    computed_scope = scope_snapshot_hash(scope)
    computed_manifest = program_manifest_hash(manifest)
    scope_match = (
        None
        if scope.canonical_sha256 is None
        else scope.canonical_sha256 == computed_scope
    )
    manifest_match = (
        None
        if manifest.manifest_sha256 is None
        else manifest.manifest_sha256 == computed_manifest
    )
    if scope_match is False:
        issues.append("stored scope canonical hash does not match computed hash")
    if manifest_match is False:
        issues.append("stored manifest canonical hash does not match computed hash")

    checked_pack_count = 0
    if root is None:
        if manifest.programs:
            issues.append("manifest root is required to verify referenced pack files")
    else:
        issues.extend(_validate_registry(root, manifest))
        for program in manifest.programs:
            try:
                pack_path = _safe_file(root, program.pack_path)
            except AlphaManifestValidationError as exc:
                issues.extend(exc.issues)
                continue
            checked_pack_count += 1
            if _byte_sha256(pack_path) != program.pack_sha256:
                issues.append(f"pack hash mismatch: {program.pack_ref}")

    publishable = (
        scope.template_state == "frozen_reviewed"
        and manifest.template_state == "frozen_reviewed"
        and scope.publishable
        and manifest.publishable
        and scope_match is True
        and manifest_match is True
        and checked_pack_count == len(manifest.programs)
        and not issues
    )
    if require_publishable and not publishable:
        issues.append("scope/manifest pair is not frozen and publishable")
    if issues:
        raise AlphaManifestValidationError(issues)

    blocking_reasons = sorted(
        set(scope.blocking_reasons) | set(manifest.blocking_reasons)
    )
    return AlphaManifestValidationReport(
        schema_version="alpha_manifest_validation_report.v1",
        dataset_id=manifest.dataset_id,
        scope_snapshot_id=scope.snapshot_id,
        computed_scope_sha256=computed_scope,
        stored_scope_hash_matches=scope_match,
        computed_manifest_sha256=computed_manifest,
        stored_manifest_hash_matches=manifest_match,
        checked_pack_count=checked_pack_count,
        publishable=publishable,
        blocking_reasons=blocking_reasons,
    )


def validate_alpha_manifest_files(
    *, root: Path, require_publishable: bool = False
) -> AlphaManifestValidationReport:
    scope_data = _read_json(root / "scope_snapshot.json", "scope_snapshot")
    manifest_data = _read_json(root / "manifest.json", "manifest")
    try:
        scope = AlphaScopeSnapshotV1.model_validate(scope_data)
    except ValidationError as exc:
        raise AlphaManifestValidationError(
            _pydantic_issues("scope_snapshot", exc)
        ) from exc
    try:
        manifest = AlphaProgramManifestV1.model_validate(manifest_data)
    except ValidationError as exc:
        raise AlphaManifestValidationError(
            _pydantic_issues("manifest", exc)
        ) from exc
    return validate_alpha_manifest(
        scope=scope,
        manifest=manifest,
        root=root,
        require_publishable=require_publishable,
    )
