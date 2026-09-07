from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
from pydantic import TypeAdapter, ValidationError

import backend.tests.test_phase4_candidate_importer as importer_support
import backend.tests.test_phase4_program_pack_contract as pack_support
import backend.tests.test_phase4_schema_compatibility as schema_support
from backend.app.db.migrations import upgrade_database
from backend.app.db.models import (
    EvidenceSupportScope,
    ProgramPublication,
    ProgramVersion,
    VersionStatus,
)
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.repositories.candidates import CandidateRepository
from backend.app.schemas.alpha_program_pack import AlphaProgramPackV1
from backend.app.schemas.candidates import CandidateCreate
from backend.app.schemas.program_fields import (
    LowAltitudeBasisFieldV1,
    ProgramTaxonomyFieldV1,
)
from backend.app.schemas.version_workflow import PublishVersionCommand, SubmitVersionCommand
from backend.app.services.alpha_low_altitude_validator import (
    AlphaLowAltitudeValidationError,
    AlphaTaxonomyEvidenceLinkView,
    AlphaTaxonomyEvidenceView,
    AlphaTaxonomyFieldView,
    validate_low_altitude_taxonomy,
)
from backend.app.services.alpha_program_pack_validator import (
    AlphaProgramPackValidationError,
    validate_alpha_program_pack,
)
from backend.app.services.version_workflow import (
    VersionLowAltitudeTaxonomyError,
    VersionWorkflowService,
)


def _pack_raw(*, low_altitude: bool = True) -> dict:
    return deepcopy(pack_support._signed_pack_raw(low_altitude=low_altitude))


def _pack(raw: dict) -> AlphaProgramPackV1:
    return AlphaProgramPackV1.model_validate(raw)


def _low_field(raw: dict) -> dict:
    return next(
        field
        for field in raw["candidate"]["fields"]
        if field["field_key"] == "taxonomy.low_altitude_basis"
    )


def _primary_field(raw: dict) -> dict:
    return next(
        field
        for field in raw["candidate"]["fields"]
        if field["field_key"] == "taxonomy.primary_direction"
    )


def _secondary_field(raw: dict) -> dict:
    return next(
        field
        for field in raw["candidate"]["fields"]
        if field["field_key"] == "taxonomy.secondary_directions"
    )


def _curriculum_evidence(raw: dict) -> dict:
    return next(
        evidence
        for evidence in raw["evidence"]
        if evidence["id"] == pack_support.CURRICULUM_EVIDENCE_ID
    )


def _views(pack: AlphaProgramPackV1):
    fields = [
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
    evidence = {
        item.id: AlphaTaxonomyEvidenceView(
            evidence_id=item.id,
            program_ref=item.program_id,
            excerpt=item.excerpt,
            reviewed_source_role=item.reviewed_source_role,
            is_v2=True,
        )
        for item in pack.evidence
    }
    return fields, evidence


def _validate_raw(raw: dict):
    return validate_alpha_program_pack(
        pack=_pack(raw),
        scope=importer_support._scope(),
    )


def test_validator_returns_strict_positive_reports_for_low_and_non_low_programs() -> None:
    low_pack = _pack(_pack_raw())
    fields, evidence = _views(low_pack)
    report = validate_low_altitude_taxonomy(
        program_ref=low_pack.program.program_ref,
        fields=fields,
        evidence_by_id=evidence,
    )
    assert report.model_dump(mode="json") == {
        "schema_version": "alpha_low_altitude_validation_report.v1",
        "program_ref": "program.synthetic.cs.01",
        "applies": True,
        "primary_direction": "low_altitude_economy",
        "secondary_directions": [],
        "inclusion_basis": "explicit_program_focus",
        "declared_subtags": ["avionics_flight_control"],
        "course_count": 1,
        "verified_course_evidence_ids": ["evidence.synthetic.curriculum"],
        "valid": True,
    }

    ordinary_pack = _pack(_pack_raw(low_altitude=False))
    fields, evidence = _views(ordinary_pack)
    ordinary = validate_low_altitude_taxonomy(
        program_ref=ordinary_pack.program.program_ref,
        fields=fields,
        evidence_by_id=evidence,
    )
    assert ordinary.applies is False
    assert ordinary.inclusion_basis is None
    assert ordinary.course_count == 0


def _curriculum_based_views(*, duplicate_course_name: bool = False):
    pack = _pack(_pack_raw())
    fields, evidence = _views(pack)
    basis_index = next(
        index
        for index, field in enumerate(fields)
        if field.field_key == "taxonomy.low_altitude_basis"
    )
    original = fields[basis_index]
    raw = original.payload.model_dump(mode="python")
    second_name = (
        "Autonomous Flight Systems"
        if duplicate_course_name
        else "Air Traffic Management"
    )
    raw["value"]["inclusion_basis"] = "curriculum_based"
    raw["value"]["subtags"] = [
        "avionics_flight_control",
        "air_traffic_management",
    ]
    raw["value"]["courses"].append(
        {
            "course_name": second_name,
            "course_type": "elective",
            "subtag": "air_traffic_management",
            "evidence_id": "evidence.synthetic.curriculum.two",
        }
    )
    raw["reviewed_source_ids"].append("evidence.synthetic.curriculum.two")
    payload = LowAltitudeBasisFieldV1.model_validate(raw)
    fields[basis_index] = replace(
        original,
        payload=payload,
        evidence_links=(
            *original.evidence_links,
            AlphaTaxonomyEvidenceLinkView(
                evidence_id="evidence.synthetic.curriculum.two",
                support_scope=EvidenceSupportScope.DIRECT,
            ),
        ),
    )
    evidence["evidence.synthetic.curriculum.two"] = AlphaTaxonomyEvidenceView(
        evidence_id="evidence.synthetic.curriculum.two",
        program_ref=pack.program.program_ref,
        excerpt=f"{second_name} is an elective course.",
        reviewed_source_role="curriculum",
        is_v2=True,
    )
    return pack, fields, evidence


def test_curriculum_based_accepts_two_independent_supported_courses() -> None:
    pack, fields, evidence = _curriculum_based_views()
    report = validate_low_altitude_taxonomy(
        program_ref=pack.program.program_ref,
        fields=fields,
        evidence_by_id=evidence,
    )
    assert report.inclusion_basis == "curriculum_based"
    assert report.course_count == 2
    assert report.verified_course_evidence_ids == [
        "evidence.synthetic.curriculum",
        "evidence.synthetic.curriculum.two",
    ]


def test_distinct_evidence_ids_cannot_make_one_course_count_as_two() -> None:
    pack, fields, evidence = _curriculum_based_views(duplicate_course_name=True)
    with pytest.raises(
        AlphaLowAltitudeValidationError,
        match="LOW_ALTITUDE_COURSE_NAME_DUPLICATE",
    ):
        validate_low_altitude_taxonomy(
            program_ref=pack.program.program_ref,
            fields=fields,
            evidence_by_id=evidence,
        )


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda raw: _curriculum_evidence(raw).__setitem__(
                "reviewed_source_role", "program"
            ),
            "LOW_ALTITUDE_COURSE_EVIDENCE_NOT_CURRICULUM",
        ),
        (
            lambda raw: next(
                link
                for link in _low_field(raw)["evidence_links"]
                if link["evidence_id"] == pack_support.CURRICULUM_EVIDENCE_ID
            ).__setitem__("support_scope", "applicability"),
            "LOW_ALTITUDE_COURSE_EVIDENCE_NOT_DIRECT",
        ),
        (
            lambda raw: _curriculum_evidence(raw).__setitem__(
                "excerpt", "A core course with no quoted course title. 已人工核对课程结构，该课程支持低空方向分类。"
            ),
            "LOW_ALTITUDE_COURSE_NAME_NOT_IN_EXCERPT",
        ),
        (
            lambda raw: _curriculum_evidence(raw).__setitem__(
                "excerpt", "Autonomous Flight Systems is offered. 已人工核对课程结构，该课程支持低空方向分类。"
            ),
            "LOW_ALTITUDE_COURSE_TYPE_NOT_IN_EXCERPT",
        ),
        (
            lambda raw: (
                _low_field(raw)["value_payload"]["value"].__setitem__(
                    "rationale_zh", "Human review says this supports the classification."
                ),
                _low_field(raw).__setitem__(
                    "display_text", "Human review says this supports the classification."
                ),
                _curriculum_evidence(raw).__setitem__(
                    "excerpt",
                    "Autonomous Flight Systems is a core course. Human review says this supports the classification.",
                ),
            ),
            "LOW_ALTITUDE_RATIONALE_NOT_CHINESE",
        ),
        (
            lambda raw: _low_field(raw)["value_payload"]["value"]["subtags"].append(
                "low_altitude_safety_systems"
            ),
            "LOW_ALTITUDE_SUBTAG_WITHOUT_COURSE",
        ),
        (
            lambda raw: (
                _low_field(raw)["value_payload"].__setitem__(
                    "reviewed_source_ids", [pack_support.CURRICULUM_EVIDENCE_ID]
                ),
                _low_field(raw).__setitem__(
                    "evidence_links",
                    [
                        link
                        for link in _low_field(raw)["evidence_links"]
                        if link["evidence_id"] == pack_support.CURRICULUM_EVIDENCE_ID
                    ],
                ),
            ),
            "LOW_ALTITUDE_EXPLICIT_FOCUS_EVIDENCE_MISSING",
        ),
    ],
)
def test_model_valid_counterexamples_fail_closed_with_stable_codes(
    mutate,
    expected_code: str,
) -> None:
    raw = _pack_raw()
    mutate(raw)
    with pytest.raises(AlphaProgramPackValidationError, match=expected_code):
        _validate_raw(raw)


def test_direction_basis_consistency_and_manual_review_fail_closed() -> None:
    missing = _pack_raw(low_altitude=False)
    secondary = _secondary_field(missing)
    secondary["value_payload"]["value"]["directions"] = ["low_altitude_economy"]
    secondary["display_text"] = "low_altitude_economy"
    missing["evidence"][0]["excerpt"] += " low_altitude_economy"
    with pytest.raises(AlphaProgramPackValidationError, match="LOW_ALTITUDE_BASIS_MISSING"):
        _validate_raw(missing)

    forbidden = _pack_raw()
    primary = _primary_field(forbidden)
    primary["value_payload"]["value"]["direction"] = "computer_science"
    primary["display_text"] = "computer_science"
    with pytest.raises(AlphaProgramPackValidationError, match="LOW_ALTITUDE_BASIS_FORBIDDEN"):
        _validate_raw(forbidden)

    manual = _pack_raw()
    field = _low_field(manual)
    note = "官网未明确课程性质，必须由领域复核人继续核验。"
    field["value_payload"].update(
        {
            "coverage_status": "manual_review",
            "value": None,
            "review_note": note,
            "reason": {
                "reason_code": "OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
                "detail": note,
            },
        }
    )
    field["display_text"] = note
    _curriculum_evidence(manual)["excerpt"] += f" {note}"
    with pytest.raises(AlphaProgramPackValidationError) as captured:
        _validate_raw(manual)
    codes = str(captured.value)
    assert "LOW_ALTITUDE_BASIS_NOT_CONFIRMED" in codes
    assert "LOW_ALTITUDE_BASIS_VALUE_MISSING" in codes


def test_curriculum_based_schema_rejects_one_broad_course_or_no_core_course() -> None:
    one_course = _pack_raw()
    _low_field(one_course)["value_payload"]["value"][
        "inclusion_basis"
    ] = "curriculum_based"
    with pytest.raises(ValidationError, match="at least two courses"):
        _pack(one_course)

    payload = deepcopy(schema_support._taxonomy_payload())
    payload["value"]["courses"][0]["course_type"] = "unknown"
    payload["value"]["courses"][1]["course_type"] = "elective"
    with pytest.raises(ValidationError, match="core or required"):
        TypeAdapter(ProgramTaxonomyFieldV1).validate_python(payload)


def test_publish_rejects_model_valid_low_altitude_candidate_without_chinese_rationale(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'low-altitude-publish.sqlite3'}"
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    ids = importer_support.SequenceIds("low-altitude-publish")
    valid_pack = _pack(_pack_raw())

    with sessions.begin() as session:
        importer_support._import(
            session,
            ids,
            valid_pack,
            "alpha-low-altitude-publish-import-key",
        )

        candidate_raw = valid_pack.candidate.model_dump(mode="python")
        candidate_raw["request_id"] = "request.low-altitude.invalid-candidate"
        low = next(
            field
            for field in candidate_raw["fields"]
            if field["field_key"] == "taxonomy.low_altitude_basis"
        )
        low["value_payload"]["value"]["rationale_zh"] = (
            "English-only rationale cannot satisfy the human Chinese review contract."
        )
        low["display_text"] = (
            "English-only rationale cannot satisfy the human Chinese review contract."
        )
        candidate = CandidateRepository(
            session,
            clock=lambda: importer_support.FIXED_NOW,
            id_factory=ids,
        ).create(
            valid_pack.program.program_ref,
            CandidateCreate.model_validate(candidate_raw),
        )
        workflow = VersionWorkflowService(
            session,
            clock=lambda: importer_support.FIXED_NOW,
            id_factory=ids,
        )
        workflow.submit(
            candidate.id,
            SubmitVersionCommand(
                submitted_by="actor.data_preparer.codex",
                submission_note="Submit model-valid synthetic counterexample.",
                request_id="request.low-altitude.invalid-submit",
            ),
        )
        with pytest.raises(
            VersionLowAltitudeTaxonomyError,
            match="LOW_ALTITUDE_RATIONALE_NOT_CHINESE",
        ):
            workflow.publish(
                candidate.id,
                PublishVersionCommand(
                    reviewed_by="actor.domain_reviewer.product_owner",
                    review_note="This must fail the low-altitude gate.",
                    request_id="request.low-altitude.invalid-publish",
                    expected_current_version_id=None,
                ),
            )

        version = session.get(ProgramVersion, candidate.id)
        assert version is not None
        assert version.status == VersionStatus.PENDING_REVIEW
        assert session.get(ProgramPublication, valid_pack.program.program_ref) is None

    engine.dispose()
