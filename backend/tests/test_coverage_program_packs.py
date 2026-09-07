from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.app.schemas.alpha_program_pack import AlphaProgramPackV1
from backend.app.services.alpha_program_pack_validator import validate_alpha_program_pack_files
from backend.app.services.internal_alpha_quality import (
    internal_alpha_manifest_hash,
    load_internal_alpha_quality_context,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALPHA_ROOT = PROJECT_ROOT / "backend" / "data" / "alpha_v1"
BATCH_PATH = ALPHA_ROOT / "candidate_batches" / "coverage_2027_batch_v1.json"
LEGACY_PACK_HASHES = {
    "pack.hk.hku.msc_computer_science.2027.v1": "df53b6fadd8deb2cbe72e4dae91a8e83e1cb2b1c26fae3c8890703532f9c0d5f",
    "pack.hk.hkust.msc_aeronautical_engineering.2027.v1": "b9304e8e0d43fd56037f5cf75ddfac6f65f3be1ba0ad99599dc7c85795d33501",
    "pack.hk.hkust.msc_artificial_intelligence.2027.v1": "14ac0eb791b6c85b8b541133f73bcf10715d2f0178d8426b3c383322e0c85dec",
    "pack.hk.hkust.msc_information_technology.2027.v1": "dd1ebc818edb17d0c8ebdc5d37e2638f3999b3c67b48c5277831aec2ebe70dd2",
    "pack.uk.manchester.msc_advanced_computer_science.2027.v1": "8db15baba5fb48745bfcc7f8584e18a4eda53808cd205c4111c96d5e5d4631db",
    "pack.uk.manchester.msc_aerospace_engineering.2027.v1": "b85dc0653cce1a767eb39541f4ee658669984bc8c5af71f1d46d9e9336ad0e97",
}


def test_reviewed_batch_materializes_as_fourteen_candidate_only_packs() -> None:
    batch = json.loads(BATCH_PATH.read_text(encoding="utf-8"))
    context = load_internal_alpha_quality_context(
        root=ALPHA_ROOT, generated_commit="coverage-pack-test"
    )
    additions = {item["pack_ref"] for item in batch["candidates"]}

    assert context.manifest.dataset_id == "dataset.internal_alpha.2027.v3"
    assert context.manifest.program_count == 20
    assert context.manifest.public_publishable is False
    assert len(additions) == 14
    assert additions.issubset(context.packs_by_ref)
    assert context.manifest.manifest_sha256 == internal_alpha_manifest_hash(context.manifest)

    entries = {item.pack_ref: item for item in context.manifest.programs}
    for pack_ref in additions:
        entry = entries[pack_ref]
        pack = context.packs_by_ref[pack_ref]
        report = validate_alpha_program_pack_files(
            pack_path=ALPHA_ROOT / entry.pack_path,
            scope_path=ALPHA_ROOT / "scope_snapshot.json",
        )
        assert report.valid is True
        assert pack.review.review_status == "approved"
        assert pack.candidate.base_version_id is None
        assert all(item.capture_method == "automated_web_candidate" for item in pack.evidence)
        assert context.pack_file_sha256_by_ref[pack_ref] == hashlib.sha256(
            (ALPHA_ROOT / entry.pack_path).read_bytes()
        ).hexdigest()


def test_original_six_packs_remain_an_unchanged_manifest_subset() -> None:
    context = load_internal_alpha_quality_context(
        root=ALPHA_ROOT, generated_commit="coverage-legacy-test"
    )
    actual = {
        item.pack_ref: item.pack_canonical_sha256
        for item in context.manifest.programs
        if item.pack_ref in LEGACY_PACK_HASHES
    }
    assert actual == LEGACY_PACK_HASHES


def test_new_programs_keep_unpublished_2027_requirements_unresolved() -> None:
    batch = json.loads(BATCH_PATH.read_text(encoding="utf-8"))
    additions = {item["pack_ref"] for item in batch["candidates"]}
    context = load_internal_alpha_quality_context(
        root=ALPHA_ROOT, generated_commit="coverage-unresolved-test"
    )
    refreshed_pack_ref = "pack.hk.hku.msc_artificial_intelligence.2027.v1"
    for pack_ref in additions - {refreshed_pack_ref}:
        pack: AlphaProgramPackV1 = context.packs_by_ref[pack_ref]
        requirement_fields = [
            field for field in pack.candidate.fields if field.field_key.startswith("requirements.")
        ]
        assert requirement_fields
        assert all(
            field.value_payload.coverage_status in {"manual_review", "not_yet_published"}
            for field in requirement_fields
        )
        assert all(not field.value_payload.requirements for field in requirement_fields)


def test_hku_ai_2027_refresh_is_evidence_backed_and_candidate_only() -> None:
    context = load_internal_alpha_quality_context(
        root=ALPHA_ROOT, generated_commit="hku-ai-refresh-test"
    )
    pack_ref = "pack.hk.hku.msc_artificial_intelligence.2027.v1"
    pack = context.packs_by_ref[pack_ref]
    entry = next(item for item in context.manifest.programs if item.pack_ref == pack_ref)
    fields = {item.field_key: item for item in pack.candidate.fields}

    assert entry.candidate_version_id == "version.hku.mscai.2027.refresh.v1"
    assert pack.candidate.base_version_id is None
    assert {item.url for item in pack.evidence} == {
        "https://www.mscai.hku.hk/admissions/",
        "https://portal.hku.hk/tpg-admissions/applying/admission-requirements",
    }
    assert all(len(item.snapshot_sha256) == 64 for item in pack.evidence)
    assert {
        key
        for key, field in fields.items()
        if getattr(field.value_payload, "coverage_status", None) == "confirmed"
    } == {
        "catalog.academic_year",
        "catalog.application_status",
        "catalog.degree_type",
        "requirements.degree",
        "requirements.language",
        "requirements.prerequisite_courses",
        "taxonomy.primary_direction",
        "taxonomy.secondary_directions",
    }
