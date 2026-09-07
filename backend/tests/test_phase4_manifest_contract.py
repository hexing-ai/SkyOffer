from __future__ import annotations

import hashlib
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.rules.canonical import content_hash
from backend.app.schemas.alpha_manifest import (
    AlphaProgramManifestV1,
    AlphaScopeSnapshotV1,
    derive_matrix_counts,
)
from backend.app.schemas.field_registry import REGISTRY_PATH
from backend.app.services.alpha_manifest_validator import (
    AlphaManifestValidationError,
    program_manifest_hash,
    scope_snapshot_hash,
    validate_alpha_manifest,
    validate_alpha_manifest_files,
)


DATA_ROOT = REGISTRY_PATH.parent


def _sample_and_review_plan() -> tuple[dict, dict, dict]:
    manifest = json.loads((DATA_ROOT / "manifest.json").read_text(encoding="utf-8"))
    return (
        manifest["field_registry"],
        manifest["sample_plan"],
        manifest["review_plan"],
    )


def _frozen_scope_raw() -> dict:
    return {
        "schema_version": "alpha_scope_snapshot.v1",
        "template_state": "frozen_reviewed",
        "publishable": True,
        "snapshot_id": "scope.alpha.synthetic.2027.v1",
        "target_academic_year": "2027-28",
        "captured_at": "2026-09-02",
        "reviewed_by": "actor.domain_reviewer.product_owner",
        "reviewed_at": "2026-09-02T12:00:00+08:00",
        "hong_kong_eight": {
            "scope_name": "hong_kong_eight",
            "institutions": [
                {
                    "institution_ref": f"institution.synthetic.hk.{index:02d}",
                    "official_name": f"Synthetic Hong Kong Institution {index:02d}",
                    "region": "hong_kong",
                    "registered_official_domain": f"hk{index}.example.edu.hk",
                }
                for index in range(1, 9)
            ],
        },
        "united_kingdom_qs_top_100": {
            "ranking_provider": "QS",
            "ranking_edition": "2027",
            "source_url": "https://www.topuniversities.com/world-university-rankings",
            "source_file_sha256": "a" * 64,
            "institutions": [
                {
                    "institution_ref": f"institution.synthetic.uk.{index:02d}",
                    "official_name": f"Synthetic United Kingdom Institution {index:02d}",
                    "region": "united_kingdom",
                    "registered_official_domain": f"uk{index}.example.ac.uk",
                    "qs_rank": index,
                }
                for index in range(1, 7)
            ],
        },
        "canonical_sha256": "0" * 64,
        "blocking_reasons": [],
    }


def _build_frozen_fixture(root: Path) -> tuple[dict, dict]:
    (root / "programs").mkdir(parents=True)
    shutil.copyfile(REGISTRY_PATH, root / "program_field_registry.v1.json")

    scope_raw = _frozen_scope_raw()
    scope = AlphaScopeSnapshotV1.model_validate(scope_raw)
    scope_raw["canonical_sha256"] = scope_snapshot_hash(scope)

    directions = (
        "computer_science",
        "artificial_intelligence",
        "aerospace_engineering",
        "low_altitude_economy",
    )
    programs: list[dict] = []
    for index in range(1, 21):
        pack_ref = f"pack.synthetic.{index:02d}"
        pack_path = root / "programs" / f"{pack_ref}.json"
        pack_path.write_text(
            json.dumps(
                {"synthetic_pack_ref": pack_ref, "test_only": True},
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        if index <= 8:
            region = "hong_kong"
            institution_index = ((index - 1) % 4) + 1
            institution_ref = f"institution.synthetic.hk.{institution_index:02d}"
        else:
            region = "united_kingdom"
            institution_index = ((index - 9) % 6) + 1
            institution_ref = f"institution.synthetic.uk.{institution_index:02d}"
        programs.append(
            {
                "pack_ref": pack_ref,
                "pack_path": f"programs/{pack_ref}.json",
                "pack_sha256": hashlib.sha256(pack_path.read_bytes()).hexdigest(),
                "program_ref": f"program.synthetic.{index:02d}",
                "institution_ref": institution_ref,
                "region": region,
                "degree_type": "taught_masters",
                "primary_direction": directions[(index - 1) % len(directions)],
                "secondary_directions": [],
                "replaces_pack_ref": None,
                "replacement_reason": None,
            }
        )

    field_registry, sample_plan, review_plan = _sample_and_review_plan()
    manifest_without_counts = {
        "schema_version": "alpha_program_manifest.v1",
        "template_state": "candidate_unreviewed",
        "publishable": False,
        "dataset_id": "dataset.alpha.synthetic.2027.v1",
        "target_academic_year": "2027-28",
        "scope_snapshot_id": scope_raw["snapshot_id"],
        "field_registry": field_registry,
        "sample_plan": sample_plan,
        "review_plan": review_plan,
        "programs": programs,
        "matrix_counts": {
            "program_count": 0,
            "hong_kong_programs": 0,
            "united_kingdom_programs": 0,
            "hong_kong_institutions": 0,
            "united_kingdom_institutions": 0,
            "primary_direction_counts": {
                direction: 0 for direction in directions
            },
        },
        "coverage_gaps": ["Synthetic fixture intentionally uses 20 rather than 24 packs."],
        "manifest_sha256": None,
        "frozen_by": None,
        "frozen_at": None,
        "blocking_reasons": ["Synthetic candidate has not been frozen."],
    }
    candidate_programs = [
        item
        for item in AlphaProgramManifestV1.model_validate(
            {
                **manifest_without_counts,
                "matrix_counts": {
                    "program_count": 20,
                    "hong_kong_programs": 8,
                    "united_kingdom_programs": 12,
                    "hong_kong_institutions": 4,
                    "united_kingdom_institutions": 6,
                    "primary_direction_counts": {
                        direction: 5 for direction in directions
                    },
                },
            }
        ).programs
    ]
    counts = derive_matrix_counts(candidate_programs).model_dump(mode="json")
    manifest_raw = {
        **manifest_without_counts,
        "template_state": "frozen_reviewed",
        "publishable": True,
        "matrix_counts": counts,
        "manifest_sha256": "0" * 64,
        "frozen_by": "actor.domain_reviewer.product_owner",
        "frozen_at": "2026-09-02T12:30:00+08:00",
        "blocking_reasons": [],
    }
    manifest = AlphaProgramManifestV1.model_validate(manifest_raw)
    manifest_raw["manifest_sha256"] = program_manifest_hash(manifest)
    return scope_raw, manifest_raw


def test_committed_frozen_scope_and_empty_manifest_fail_closed() -> None:
    scope = AlphaScopeSnapshotV1.model_validate_json(
        (DATA_ROOT / "scope_snapshot.json").read_text(encoding="utf-8")
    )
    manifest = AlphaProgramManifestV1.model_validate_json(
        (DATA_ROOT / "manifest.json").read_text(encoding="utf-8")
    )
    assert scope.template_state == "frozen_reviewed"
    assert scope.publishable is True
    assert scope.canonical_sha256 == scope_snapshot_hash(scope)
    assert len(scope.hong_kong_eight.institutions) == 8
    assert len(scope.united_kingdom_qs_top_100.institutions) == 6
    assert manifest.template_state == "empty_unreviewed"
    assert manifest.publishable is False
    assert manifest.scope_snapshot_id is None
    assert manifest.programs == []

    with pytest.raises(
        AlphaManifestValidationError,
        match="manifest scope_snapshot_id does not match scope snapshot_id",
    ):
        validate_alpha_manifest_files(root=DATA_ROOT)


def test_frozen_scope_manifest_and_pack_hashes_validate_offline(tmp_path) -> None:
    scope_raw, manifest_raw = _build_frozen_fixture(tmp_path)
    scope = AlphaScopeSnapshotV1.model_validate(scope_raw)
    manifest = AlphaProgramManifestV1.model_validate(manifest_raw)
    report = validate_alpha_manifest(
        scope=scope, manifest=manifest, root=tmp_path, require_publishable=True
    )
    assert report.publishable is True
    assert report.checked_pack_count == 20
    assert report.stored_scope_hash_matches is True
    assert report.stored_manifest_hash_matches is True
    assert report.blocking_reasons == []


def test_json_key_and_list_order_do_not_change_semantic_hashes(tmp_path) -> None:
    scope_raw, manifest_raw = _build_frozen_fixture(tmp_path)
    original_scope = AlphaScopeSnapshotV1.model_validate(scope_raw)
    original_manifest = AlphaProgramManifestV1.model_validate(manifest_raw)

    reordered_scope = deepcopy(scope_raw)
    reordered_scope["hong_kong_eight"]["institutions"].reverse()
    reordered_scope["united_kingdom_qs_top_100"]["institutions"].reverse()
    reordered_scope = dict(reversed(list(reordered_scope.items())))
    reordered_manifest = deepcopy(manifest_raw)
    reordered_manifest["programs"].reverse()
    reordered_manifest = dict(reversed(list(reordered_manifest.items())))

    parsed_scope = AlphaScopeSnapshotV1.model_validate(reordered_scope)
    parsed_manifest = AlphaProgramManifestV1.model_validate(reordered_manifest)
    assert scope_snapshot_hash(parsed_scope) == scope_snapshot_hash(original_scope)
    assert program_manifest_hash(parsed_manifest) == program_manifest_hash(
        original_manifest
    )
    validate_alpha_manifest(
        scope=parsed_scope,
        manifest=parsed_manifest,
        root=tmp_path,
        require_publishable=True,
    )


def test_scope_normalizes_aliases_and_rejects_cross_institution_domain_reuse() -> None:
    raw = _frozen_scope_raw()
    raw["united_kingdom_qs_top_100"]["institutions"][0][
        "official_domain_aliases"
    ] = ["Alias.Example.Ac.Uk."]
    parsed = AlphaScopeSnapshotV1.model_validate(raw)
    assert (
        parsed.united_kingdom_qs_top_100.institutions[0].official_domain_aliases
        == ["alias.example.ac.uk"]
    )

    reused = deepcopy(raw)
    reused["united_kingdom_qs_top_100"]["institutions"][1][
        "official_domain_aliases"
    ] = ["alias.example.ac.uk"]
    with pytest.raises(ValidationError, match="aliases must be globally unique"):
        AlphaScopeSnapshotV1.model_validate(reused)

    overlapping = deepcopy(raw)
    overlapping["united_kingdom_qs_top_100"]["institutions"][1][
        "official_domain_aliases"
    ] = ["catalog.uk1.example.ac.uk"]
    with pytest.raises(ValidationError, match="aliases must be globally unique"):
        AlphaScopeSnapshotV1.model_validate(overlapping)


def test_committed_candidate_matrix_v2_hash_and_scope_reference_are_frozen() -> None:
    matrix = json.loads(
        (
            DATA_ROOT
            / "sources"
            / "alpha_program_candidate_matrix_2027_v1.json"
        ).read_text(encoding="utf-8")
    )
    stored_hash = matrix.pop("matrix_sha256")

    assert matrix["matrix_id"] == "matrix.alpha.2027.v2"
    assert matrix["scope_snapshot_id"] == "scope.alpha.2027.v2"
    assert len(matrix["programs"]) == 24
    assert content_hash(matrix["programs"]) == (
        "cc9b8041a1ef3474b1e93e5abf9c7295811e17e3407e55550df0288276ba592c"
    )
    assert stored_hash == content_hash(matrix)


def test_pack_mutation_invalidates_pack_and_manifest_hash_chain(tmp_path) -> None:
    scope_raw, manifest_raw = _build_frozen_fixture(tmp_path)
    scope = AlphaScopeSnapshotV1.model_validate(scope_raw)
    manifest = AlphaProgramManifestV1.model_validate(manifest_raw)
    first_program = manifest.programs[0]
    pack_path = tmp_path / first_program.pack_path
    pack_path.write_bytes(pack_path.read_bytes() + b"\nchanged")

    with pytest.raises(AlphaManifestValidationError, match="pack hash mismatch"):
        validate_alpha_manifest(scope=scope, manifest=manifest, root=tmp_path)

    changed_manifest_raw = deepcopy(manifest_raw)
    changed_entry = next(
        item
        for item in changed_manifest_raw["programs"]
        if item["pack_ref"] == first_program.pack_ref
    )
    changed_entry["pack_sha256"] = hashlib.sha256(pack_path.read_bytes()).hexdigest()
    changed_manifest = AlphaProgramManifestV1.model_validate(changed_manifest_raw)
    assert program_manifest_hash(changed_manifest) != manifest_raw["manifest_sha256"]
    with pytest.raises(
        AlphaManifestValidationError, match="stored manifest canonical hash"
    ):
        validate_alpha_manifest(
            scope=scope, manifest=changed_manifest, root=tmp_path
        )


def test_contract_rejects_matrix_identity_path_and_scope_drift(tmp_path) -> None:
    scope_raw, manifest_raw = _build_frozen_fixture(tmp_path)

    wrong_matrix = deepcopy(manifest_raw)
    wrong_matrix["matrix_counts"]["program_count"] = 19
    with pytest.raises(ValidationError, match="matrix_counts"):
        AlphaProgramManifestV1.model_validate(wrong_matrix)

    duplicate_ref = deepcopy(manifest_raw)
    duplicate_ref["programs"][1]["program_ref"] = duplicate_ref["programs"][0][
        "program_ref"
    ]
    with pytest.raises(ValidationError, match="program_ref values must be unique"):
        AlphaProgramManifestV1.model_validate(duplicate_ref)

    traversal = deepcopy(manifest_raw)
    traversal["programs"][0]["pack_path"] = "../outside.json"
    with pytest.raises(ValidationError, match="direct JSON child"):
        AlphaProgramManifestV1.model_validate(traversal)

    outside_scope = deepcopy(manifest_raw)
    outside_scope["programs"][0]["institution_ref"] = "institution.synthetic.outside"
    outside_scope["matrix_counts"]["hong_kong_institutions"] = 5
    outside_manifest = AlphaProgramManifestV1.model_validate(outside_scope)
    scope = AlphaScopeSnapshotV1.model_validate(scope_raw)
    with pytest.raises(AlphaManifestValidationError, match="outside scope"):
        validate_alpha_manifest(
            scope=scope, manifest=outside_manifest, root=tmp_path
        )


def test_frozen_matrix_cannot_lower_approved_sample_minimums(tmp_path) -> None:
    _, manifest_raw = _build_frozen_fixture(tmp_path)
    too_few_directions = deepcopy(manifest_raw)
    for item in too_few_directions["programs"]:
        if item["primary_direction"] == "low_altitude_economy":
            item["primary_direction"] = "computer_science"
    candidate = deepcopy(too_few_directions)
    candidate["template_state"] = "candidate_unreviewed"
    candidate["publishable"] = False
    candidate["manifest_sha256"] = None
    candidate["frozen_by"] = None
    candidate["frozen_at"] = None
    candidate["blocking_reasons"] = ["Synthetic matrix is incomplete."]
    parsed_programs = AlphaProgramManifestV1.model_validate(
        {
            **candidate,
            "matrix_counts": {
                **candidate["matrix_counts"],
                "primary_direction_counts": {
                    "computer_science": 10,
                    "artificial_intelligence": 5,
                    "aerospace_engineering": 5,
                    "low_altitude_economy": 0,
                },
            },
        }
    ).programs
    too_few_directions["matrix_counts"] = derive_matrix_counts(
        parsed_programs
    ).model_dump(mode="json")
    with pytest.raises(ValidationError, match="does not cover every primary direction"):
        AlphaProgramManifestV1.model_validate(too_few_directions)
