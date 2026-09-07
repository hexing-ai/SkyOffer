from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.schemas.alpha_manifest import AlphaScopeSnapshotV1
from backend.app.schemas.alpha_program_pack import AlphaProgramPackV1
from backend.app.schemas.field_registry import load_program_field_registry
from backend.app.services.alpha_manifest_validator import scope_snapshot_hash
from backend.app.services.alpha_program_pack_validator import (
    AlphaProgramPackValidationError,
    alpha_program_pack_hash,
    alpha_program_pack_semantic_hash,
    validate_alpha_program_pack,
    validate_alpha_program_pack_files,
)


PROGRAM_EVIDENCE_ID = "evidence.synthetic.program"
CURRICULUM_EVIDENCE_ID = "evidence.synthetic.curriculum"


def _frozen_scope_raw() -> dict:
    raw = {
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
    scope = AlphaScopeSnapshotV1.model_validate(raw)
    raw["canonical_sha256"] = scope_snapshot_hash(scope)
    return raw


def _evidence(evidence_id: str, *, curriculum: bool = False) -> dict:
    excerpt = (
        "Autonomous Flight Systems is a core course."
        if curriculum
        else "2027-28 taught_masters Computing 12 full_time September open "
        "computer_science no secondary direction."
    )
    role = "curriculum" if curriculum else "program"
    suffix = "curriculum" if curriculum else "program"
    return {
        "schema_version": "source_evidence.v2",
        "applicable_academic_year": "2027-28",
        "id": evidence_id,
        "program_id": "program.synthetic.cs.01",
        "source_type": "official_program_page",
        "url": f"https://www.hk1.example.edu.hk/{suffix}",
        "official_domain": "www.hk1.example.edu.hk",
        "page_title": f"Synthetic {suffix.title()} Page",
        "excerpt": excerpt,
        "snapshot_sha256": ("b" if curriculum else "a") * 64,
        "source_version": "2027 admissions cycle",
        "captured_at": "2026-09-02T09:00:00+08:00",
        "verified_at": "2026-09-02T09:30:00+08:00",
        "verified_by": "actor.data_preparer.codex",
        "review_due_at": "2026-12-01T09:30:00+08:00",
        "expires_at": "2027-03-01T09:30:00+08:00",
        "availability_at_verification": "available",
        "capture_method": "manual_browser",
        "hash_scope": "normalized_excerpt",
        "reviewed_source_role": role,
    }


def _links(source_ids: list[str], scope: str) -> list[dict]:
    return [
        {"evidence_id": evidence_id, "support_scope": scope, "citation_order": index}
        for index, evidence_id in enumerate(source_ids, start=1)
    ]


def _catalog_field(
    field_key: str,
    value: dict,
    display_text: str,
    source_ids: list[str],
) -> dict:
    registry = load_program_field_registry().definition_for(field_key)
    return {
        "field_key": field_key,
        "value_schema_version": "program_catalog_field.v1",
        "value_payload": {
            "schema_version": "program_catalog_field.v1",
            "field_key": field_key,
            "applicable_academic_year": "2027-28",
            "coverage_status": "confirmed",
            "value": value,
            "reviewed_source_ids": source_ids,
            "review_note": None,
            "reason": None,
        },
        "display_text": display_text,
        "is_critical": registry.is_critical,
        "evidence_links": _links(source_ids, "direct"),
    }


def _taxonomy_field(
    field_key: str,
    value: dict,
    display_text: str,
    source_ids: list[str],
) -> dict:
    registry = load_program_field_registry().definition_for(field_key)
    return {
        "field_key": field_key,
        "value_schema_version": "program_taxonomy_field.v1",
        "value_payload": {
            "schema_version": "program_taxonomy_field.v1",
            "field_key": field_key,
            "applicable_academic_year": "2027-28",
            "coverage_status": "confirmed",
            "value": value,
            "reviewed_source_ids": source_ids,
            "review_note": None,
            "reason": None,
        },
        "display_text": display_text,
        "is_critical": registry.is_critical,
        "evidence_links": _links(source_ids, "direct"),
    }


def _requirement_field(field_key: str, source_ids: list[str]) -> dict:
    registry = load_program_field_registry().definition_for(field_key)
    detail = "No requirement was found in the complete reviewed source set."
    return {
        "field_key": field_key,
        "value_schema_version": "program_requirement_field.v2",
        "value_payload": {
            "schema_version": "program_requirement_field.v2",
            "field_key": field_key,
            "applicable_academic_year": "2027-28",
            "coverage_status": "not_found_in_reviewed_sources",
            "requirements": [],
            "reviewed_source_ids": source_ids,
            "review_note": detail,
            "reason": {"reason_code": "OFFICIAL_RULE_NOT_FOUND", "detail": detail},
        },
        "display_text": detail,
        "is_critical": registry.is_critical,
        "evidence_links": _links(source_ids, "coverage"),
    }


def _all_required_fields(source_ids: list[str]) -> list[dict]:
    fields = [
        _catalog_field(
            "catalog.academic_year", {"academic_year": "2027-28"}, "2027-28", source_ids
        ),
        _catalog_field(
            "catalog.degree_type", {"degree_type": "taught_masters"}, "taught_masters", source_ids
        ),
        _catalog_field(
            "catalog.department", {"department_name": "Computing"}, "Computing", source_ids
        ),
        _catalog_field(
            "catalog.duration", {"months": 12, "study_mode": "full_time"}, "12 full_time", source_ids
        ),
        _catalog_field(
            "catalog.intake", {"intake_months": [9]}, "September", source_ids
        ),
        _catalog_field(
            "catalog.application_status", {"status": "open", "opens_on": None, "closes_on": None}, "open", source_ids
        ),
        _taxonomy_field(
            "taxonomy.primary_direction", {"direction": "computer_science"}, "computer_science", source_ids
        ),
        _taxonomy_field(
            "taxonomy.secondary_directions", {"directions": []}, "no secondary direction", source_ids
        ),
    ]
    fields.extend(
        _requirement_field(field_key, source_ids)
        for field_key in (
            "requirements.degree",
            "requirements.academic",
            "requirements.subject",
            "requirements.prerequisite_courses",
            "requirements.language",
            "requirements.work_experience",
            "requirements.materials",
        )
    )
    return fields


def _unsigned_pack_raw(*, low_altitude: bool = False) -> dict:
    source_ids = [PROGRAM_EVIDENCE_ID]
    evidence = [_evidence(PROGRAM_EVIDENCE_ID)]
    fields = _all_required_fields(source_ids)
    if low_altitude:
        source_ids.append(CURRICULUM_EVIDENCE_ID)
        evidence.append(_evidence(CURRICULUM_EVIDENCE_ID, curriculum=True))
        fields = _all_required_fields(source_ids)
        primary = next(
            item for item in fields if item["field_key"] == "taxonomy.primary_direction"
        )
        primary["value_payload"]["value"]["direction"] = "low_altitude_economy"
        primary["display_text"] = "low_altitude_economy"
        evidence[0]["excerpt"] += " low_altitude_economy"
        fields.append(
            _taxonomy_field(
                "taxonomy.low_altitude_basis",
                {
                    "inclusion_basis": "explicit_program_focus",
                    "subtags": ["avionics_flight_control"],
                    "rationale_zh": "已人工核对课程结构，该课程支持低空方向分类。",
                    "courses": [
                        {
                            "course_name": "Autonomous Flight Systems",
                            "course_type": "core",
                            "subtag": "avionics_flight_control",
                            "evidence_id": CURRICULUM_EVIDENCE_ID,
                        }
                    ],
                    "counterexample_check_completed": True,
                },
                "已人工核对课程结构，该课程支持低空方向分类。",
                source_ids,
            )
        )
    return {
        "schema_version": "alpha_program_pack.v1",
        "pack_ref": "pack.synthetic.cs.01",
        "scope_snapshot_id": "scope.alpha.synthetic.2027.v1",
        "scope_institution_ref": "institution.synthetic.hk.01",
        "target_academic_year": "2027-28",
        "program": {
            "program_ref": "program.synthetic.cs.01",
            "official_name": "Synthetic MSc Computer Science",
            "institution_name": "Synthetic Hong Kong Institution 01",
            "region": "hong_kong",
            "official_program_url": "https://www.hk1.example.edu.hk/program",
            "registered_official_domain": "hk1.example.edu.hk",
            "degree_type": "taught_masters",
            "created_by": "actor.data_preparer.codex",
            "creation_note": "Synthetic test-only Program payload.",
        },
        "reviewed_source_ids": source_ids,
        "evidence": evidence,
        "candidate": {
            "base_version_id": None,
            "fields": fields,
            "created_by": "actor.data_preparer.codex",
            "creation_note": "Synthetic test-only Candidate payload.",
            "request_id": "request.synthetic.pack.01",
        },
        "review": {
            "prepared_by": "actor.data_preparer.codex",
            "prepared_at": "2026-09-02T10:00:00+08:00",
            "reviewed_by": "actor.domain_reviewer.product_owner",
            "reviewed_at": "2026-09-02T11:00:00+08:00",
            "review_note": "Synthetic Pack reviewed for contract validation only.",
            "review_status": "approved",
        },
        "pack_canonical_sha256": "0" * 64,
        "expected_semantic_content_sha256": "0" * 64,
    }


def _signed_pack_raw(*, low_altitude: bool = False) -> dict:
    raw = _unsigned_pack_raw(low_altitude=low_altitude)
    pack = AlphaProgramPackV1.model_validate(raw)
    raw["expected_semantic_content_sha256"] = alpha_program_pack_semantic_hash(pack)
    pack = AlphaProgramPackV1.model_validate(raw)
    raw["pack_canonical_sha256"] = alpha_program_pack_hash(pack)
    return raw


def _validate_raw(raw: dict) -> None:
    pack = AlphaProgramPackV1.model_validate(raw)
    scope = AlphaScopeSnapshotV1.model_validate(_frozen_scope_raw())
    validate_alpha_program_pack(pack=pack, scope=scope)


def test_single_synthetic_pack_validates_offline_and_is_deterministic() -> None:
    raw = _signed_pack_raw()
    pack = AlphaProgramPackV1.model_validate(raw)
    scope = AlphaScopeSnapshotV1.model_validate(_frozen_scope_raw())
    first = validate_alpha_program_pack(pack=pack, scope=scope)
    second = validate_alpha_program_pack(pack=pack, scope=scope)
    assert first == second
    assert first.valid is True
    assert first.field_count == 15
    assert first.evidence_count == 1


def test_pack_accepts_evidence_from_scope_reviewed_official_domain_alias() -> None:
    scope_raw = _frozen_scope_raw()
    institution = scope_raw["hong_kong_eight"]["institutions"][0]
    institution["official_domain_aliases"] = ["hk1-alias.example.edu.hk"]
    scope = AlphaScopeSnapshotV1.model_validate(scope_raw)
    scope_raw["canonical_sha256"] = scope_snapshot_hash(scope)
    scope = AlphaScopeSnapshotV1.model_validate(scope_raw)

    raw = _signed_pack_raw()
    raw["program"]["official_domain_aliases"] = ["hk1-alias.example.edu.hk"]
    evidence = raw["evidence"][0]
    evidence["url"] = "https://catalog.hk1-alias.example.edu.hk/program"
    evidence["official_domain"] = "catalog.hk1-alias.example.edu.hk"
    pack = AlphaProgramPackV1.model_validate(raw)
    raw["expected_semantic_content_sha256"] = alpha_program_pack_semantic_hash(pack)
    pack = AlphaProgramPackV1.model_validate(raw)
    raw["pack_canonical_sha256"] = alpha_program_pack_hash(pack)

    report = validate_alpha_program_pack(
        pack=AlphaProgramPackV1.model_validate(raw), scope=scope
    )
    assert report.valid is True


def test_pack_rejects_evidence_from_undeclared_official_domain_alias() -> None:
    raw = _signed_pack_raw()
    raw["evidence"][0]["url"] = "https://catalog.unreviewed.example.edu.hk/program"
    raw["evidence"][0]["official_domain"] = "catalog.unreviewed.example.edu.hk"
    pack = AlphaProgramPackV1.model_validate(raw)
    raw["expected_semantic_content_sha256"] = alpha_program_pack_semantic_hash(pack)
    pack = AlphaProgramPackV1.model_validate(raw)
    raw["pack_canonical_sha256"] = alpha_program_pack_hash(pack)

    with pytest.raises(
        AlphaProgramPackValidationError, match="outside the official domain"
    ):
        _validate_raw(raw)


def test_equivalent_key_field_evidence_and_link_order_has_stable_hashes() -> None:
    original_raw = _signed_pack_raw(low_altitude=True)
    reordered = deepcopy(original_raw)
    reordered["candidate"]["fields"].reverse()
    reordered["evidence"].reverse()
    reordered["reviewed_source_ids"].reverse()
    for field in reordered["candidate"]["fields"]:
        field["evidence_links"].reverse()
        field["value_payload"]["reviewed_source_ids"].reverse()
    reordered = dict(reversed(list(reordered.items())))

    original = AlphaProgramPackV1.model_validate(original_raw)
    equivalent = AlphaProgramPackV1.model_validate(reordered)
    assert alpha_program_pack_semantic_hash(equivalent) == alpha_program_pack_semantic_hash(original)
    assert alpha_program_pack_hash(equivalent) == alpha_program_pack_hash(original)
    _validate_raw(reordered)


@pytest.mark.parametrize(
    "mutation, match",
    [
        (
            lambda raw: raw["candidate"]["fields"].pop(),
            "missing mandatory fields",
        ),
        (
            lambda raw: raw.__setitem__("target_academic_year", "2026-27"),
            "Input should be '2027-28'",
        ),
        (
            lambda raw: raw.__setitem__("scope_institution_ref", "institution.synthetic.outside"),
            "outside the frozen scope",
        ),
        (
            lambda raw: raw["evidence"][0].__setitem__("program_id", "program.synthetic.other"),
            "belongs to another program",
        ),
        (
            lambda raw: raw["evidence"][0].__setitem__("applicable_academic_year", "2026-27"),
            "Input should be '2027-28'",
        ),
        (
            lambda raw: next(
                item
                for item in raw["candidate"]["fields"]
                if item["field_key"] == "catalog.duration"
            )["value_payload"].__setitem__("applicable_academic_year", "2026-27"),
            "field catalog.duration has the wrong academic year",
        ),
        (
            lambda raw: (
                raw["evidence"][0].__setitem__("url", "https://other.example.org/program"),
                raw["evidence"][0].__setitem__("official_domain", "other.example.org"),
            ),
            "outside the official domain",
        ),
        (
            lambda raw: raw["evidence"][0].__setitem__("excerpt", ""),
            "String should have at least 1 character",
        ),
        (
            lambda raw: raw.__setitem__("pack_canonical_sha256", "f" * 64),
            "stored pack canonical hash",
        ),
        (
            lambda raw: raw.__setitem__("expected_semantic_content_sha256", "f" * 64),
            "stored expected semantic content hash",
        ),
    ],
)
def test_pack_fail_closed_on_scope_year_evidence_and_hash_drift(mutation, match: str) -> None:
    raw = _signed_pack_raw()
    mutation(raw)
    with pytest.raises((ValidationError, AlphaProgramPackValidationError), match=match):
        _validate_raw(raw)


def test_confirmed_field_rejects_coverage_definition_and_non_verbatim_display() -> None:
    for support_scope in ("coverage", "definition"):
        raw = _signed_pack_raw(low_altitude=True)
        field = next(
            item for item in raw["candidate"]["fields"] if item["field_key"] == "catalog.duration"
        )
        field["evidence_links"][0]["support_scope"] = support_scope
        with pytest.raises(AlphaProgramPackValidationError, match="coverage or definition"):
            _validate_raw(raw)

    raw = _signed_pack_raw()
    field = next(
        item for item in raw["candidate"]["fields"] if item["field_key"] == "catalog.duration"
    )
    field["display_text"] = "approximately one year"
    with pytest.raises(AlphaProgramPackValidationError, match="not verbatim direct Evidence"):
        _validate_raw(raw)


def test_not_found_requires_complete_reviewed_source_set() -> None:
    raw = _signed_pack_raw(low_altitude=True)
    field = next(
        item for item in raw["candidate"]["fields"] if item["field_key"] == "requirements.degree"
    )
    field["value_payload"]["reviewed_source_ids"] = [PROGRAM_EVIDENCE_ID]
    field["evidence_links"] = _links([PROGRAM_EVIDENCE_ID], "coverage")
    with pytest.raises(AlphaProgramPackValidationError, match="complete reviewed source set"):
        _validate_raw(raw)


def test_low_altitude_requires_reviewed_direct_curriculum_course_evidence() -> None:
    _validate_raw(_signed_pack_raw(low_altitude=True))

    missing_basis = _signed_pack_raw()
    primary = next(
        item for item in missing_basis["candidate"]["fields"] if item["field_key"] == "taxonomy.primary_direction"
    )
    primary["value_payload"]["value"]["direction"] = "low_altitude_economy"
    primary["display_text"] = "low_altitude_economy"
    missing_basis["evidence"][0]["excerpt"] += " low_altitude_economy"
    with pytest.raises(AlphaProgramPackValidationError, match="requires taxonomy.low_altitude_basis"):
        _validate_raw(missing_basis)

    wrong_role = _signed_pack_raw(low_altitude=True)
    wrong_role["evidence"][1]["reviewed_source_role"] = "program"
    with pytest.raises(AlphaProgramPackValidationError, match="lacks curriculum Evidence"):
        _validate_raw(wrong_role)


def test_schema_rejects_duplicates_unknowns_research_and_review_role_drift() -> None:
    duplicate_field = _signed_pack_raw()
    duplicate_field["candidate"]["fields"].append(
        deepcopy(duplicate_field["candidate"]["fields"][0])
    )
    with pytest.raises(ValidationError, match="unique field_key"):
        AlphaProgramPackV1.model_validate(duplicate_field)

    duplicate_evidence = _signed_pack_raw()
    duplicate_evidence["evidence"].append(deepcopy(duplicate_evidence["evidence"][0]))
    duplicate_evidence["reviewed_source_ids"].append(PROGRAM_EVIDENCE_ID)
    with pytest.raises(ValidationError, match="duplicates"):
        AlphaProgramPackV1.model_validate(duplicate_evidence)

    for key, value in (
        ("schema_version", "alpha_program_pack.v999"),
        ("unexpected", True),
    ):
        raw = _signed_pack_raw()
        raw[key] = value
        with pytest.raises(ValidationError):
            AlphaProgramPackV1.model_validate(raw)

    research = _signed_pack_raw()
    research["program"]["degree_type"] = "research_masters"
    with pytest.raises(ValidationError, match="taught_masters"):
        AlphaProgramPackV1.model_validate(research)

    self_review = _signed_pack_raw()
    self_review["review"]["reviewed_by"] = "actor.data_preparer.codex"
    with pytest.raises(ValidationError, match="product_owner"):
        AlphaProgramPackV1.model_validate(self_review)


def test_semantic_hash_changes_for_fact_scope_or_snapshot_but_not_prose() -> None:
    raw = _signed_pack_raw()
    original = AlphaProgramPackV1.model_validate(raw)
    original_hash = alpha_program_pack_semantic_hash(original)

    prose = deepcopy(raw)
    prose["review"]["review_note"] = "Different non-semantic pack review prose."
    prose_pack = AlphaProgramPackV1.model_validate(prose)
    assert alpha_program_pack_semantic_hash(prose_pack) == original_hash

    snapshot = deepcopy(raw)
    snapshot["evidence"][0]["snapshot_sha256"] = "c" * 64
    assert alpha_program_pack_semantic_hash(AlphaProgramPackV1.model_validate(snapshot)) != original_hash

    support = _signed_pack_raw(low_altitude=True)
    support_original_hash = alpha_program_pack_semantic_hash(
        AlphaProgramPackV1.model_validate(support)
    )
    field = next(
        item for item in support["candidate"]["fields"] if item["field_key"] == "catalog.duration"
    )
    field["evidence_links"][0]["support_scope"] = "applicability"
    assert (
        alpha_program_pack_semantic_hash(AlphaProgramPackV1.model_validate(support))
        != support_original_hash
    )

    fact = deepcopy(raw)
    field = next(
        item for item in fact["candidate"]["fields"] if item["field_key"] == "catalog.duration"
    )
    field["value_payload"]["value"]["months"] = 18
    assert alpha_program_pack_semantic_hash(AlphaProgramPackV1.model_validate(fact)) != original_hash


def test_file_validator_failure_is_read_only_and_does_not_touch_database(tmp_path: Path) -> None:
    pack_path = tmp_path / "pack.json"
    scope_path = tmp_path / "scope.json"
    raw = _signed_pack_raw()
    raw["pack_canonical_sha256"] = "f" * 64
    pack_path.write_text(json.dumps(raw), encoding="utf-8")
    scope_path.write_text(json.dumps(_frozen_scope_raw()), encoding="utf-8")
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}

    with pytest.raises(AlphaProgramPackValidationError, match="stored pack canonical hash"):
        validate_alpha_program_pack_files(pack_path=pack_path, scope_path=scope_path)

    after = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    assert after == before
