from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

import backend.tests.test_phase3_candidates as phase3_support
from backend.app.db.migrations import upgrade_database
from backend.app.db.models import (
    Program,
    ProgramPublication,
    ProgramRegion,
    ProgramVersion,
    VersionStatus,
)
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.repositories.candidates import (
    CandidateRepository,
    _FieldSnapshot,
    _content_envelope,
    _value_hash,
)
from backend.app.repositories.evidence import SourceEvidenceRepository
from backend.app.repositories.published_programs import PublishedProgramReader
from backend.app.rules.canonical import content_hash, normalize
from backend.app.schemas.candidates import (
    CandidateCreate,
    CandidateEvidenceLinkCreate,
)
from backend.app.schemas.evidence import (
    SourceEvidenceCreate,
    SourceEvidenceCreateV2,
)
from backend.app.schemas.field_registry import (
    ProgramFieldRegistry,
    load_program_field_registry,
)
from backend.app.schemas.program_fields import (
    ProgramCatalogFieldV1,
    ProgramRequirementFieldV2,
    ProgramTaxonomyFieldV1,
)


FIXED_NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)
PROGRAM_ID = phase3_support.PROGRAM_ID


def _v2_evidence(evidence_id: str, character: str) -> SourceEvidenceCreateV2:
    raw = phase3_support._evidence(
        evidence_id, snapshot_sha256=character * 64
    )
    return SourceEvidenceCreateV2.model_validate(
        {
            "schema_version": "source_evidence.v2",
            "id": raw.id,
            "program_id": raw.program_id,
            "source_type": raw.source_type,
            "url": raw.url,
            "official_domain": raw.official_domain,
            "page_title": raw.page_title,
            "excerpt": raw.excerpt,
            "snapshot_sha256": raw.snapshot_sha256,
            "source_version": raw.source_version,
            "captured_at": raw.captured_at,
            "verified_at": raw.verified_at,
            "verified_by": raw.verified_by,
            "review_due_at": raw.review_due_at,
            "expires_at": raw.expires_at,
            "availability_at_verification": raw.availability_at_verification,
            "capture_method": "manual_browser",
            "hash_scope": "normalized_excerpt",
            "reviewed_source_role": "program",
        }
    )


def _catalog_payload() -> dict:
    return {
        "schema_version": "program_catalog_field.v1",
        "field_key": "catalog.duration",
        "applicable_academic_year": "2027-28",
        "coverage_status": "confirmed",
        "value": {"months": 12, "study_mode": "full_time"},
        "reviewed_source_ids": ["evidence.alpha.duration"],
        "review_note": None,
        "reason": None,
    }


def _requirement_payload() -> dict:
    return {
        "schema_version": "program_requirement_field.v2",
        "field_key": "requirements.language",
        "applicable_academic_year": "2027-28",
        "coverage_status": "confirmed",
        "requirements": [
            {
                "requirement_id": "requirement.alpha.language",
                "requirement_type": "language",
                "is_hard": True,
                "applicability": None,
                "rule": {
                    "node_id": "node.alpha.language.ielts",
                    "operator": "language_minimum",
                    "test_type": "ielts",
                    "total_min": "7.0",
                    "component_mins": {"writing": "6.5"},
                },
                "evidence_fixture_ids": ["evidence.alpha.language"],
                "display_text": "IELTS 总分 7.0，写作 6.5。",
            }
        ],
        "reviewed_source_ids": ["evidence.alpha.language"],
        "review_note": None,
        "reason": None,
    }


def _taxonomy_payload() -> dict:
    return {
        "schema_version": "program_taxonomy_field.v1",
        "field_key": "taxonomy.low_altitude_basis",
        "applicable_academic_year": "2027-28",
        "coverage_status": "confirmed",
        "value": {
            "inclusion_basis": "curriculum_based",
            "subtags": ["unmanned_aircraft_systems", "avionics_flight_control"],
            "rationale_zh": "两门独立课程构成低空方向支撑。",
            "courses": [
                {
                    "course_name": "Unmanned Aircraft Systems",
                    "course_type": "core",
                    "subtag": "unmanned_aircraft_systems",
                    "evidence_id": "evidence.alpha.curriculum.one",
                },
                {
                    "course_name": "Avionics and Flight Control",
                    "course_type": "elective",
                    "subtag": "avionics_flight_control",
                    "evidence_id": "evidence.alpha.curriculum.two",
                },
            ],
            "counterexample_check_completed": True,
        },
        "reviewed_source_ids": [
            "evidence.alpha.curriculum.one",
            "evidence.alpha.curriculum.two",
        ],
        "review_note": None,
        "reason": None,
    }


def _candidate_payload() -> CandidateCreate:
    return CandidateCreate.model_validate(
        {
            "base_version_id": None,
            "fields": [
                {
                    "field_key": "catalog.duration",
                    "value_schema_version": "program_catalog_field.v1",
                    "value_payload": _catalog_payload(),
                    "display_text": "全日制 12 个月。",
                    "is_critical": False,
                    "evidence_links": [
                        {
                            "evidence_id": "evidence.alpha.duration",
                            "support_scope": "direct",
                            "citation_order": 1,
                        }
                    ],
                },
                {
                    "field_key": "requirements.language",
                    "value_schema_version": "program_requirement_field.v2",
                    "value_payload": _requirement_payload(),
                    "display_text": "IELTS 总分 7.0，写作 6.5。",
                    "is_critical": True,
                    "evidence_links": [
                        {
                            "evidence_id": "evidence.alpha.language",
                            "support_scope": "direct",
                            "citation_order": 1,
                        }
                    ],
                },
                {
                    "field_key": "requirements.degree",
                    "value_schema_version": "program_requirement_field.v2",
                    "value_payload": {
                        "schema_version": "program_requirement_field.v2",
                        "field_key": "requirements.degree",
                        "applicable_academic_year": "2027-28",
                        "coverage_status": "not_found_in_reviewed_sources",
                        "requirements": [],
                        "reviewed_source_ids": ["evidence.alpha.degree.coverage"],
                        "review_note": "已核验的官方来源中未找到明确学位规则。",
                        "reason": {
                            "reason_code": "OFFICIAL_RULE_NOT_FOUND",
                            "detail": "已核验的官方来源中未找到明确学位规则。",
                        },
                    },
                    "display_text": "已核验的官方来源中未找到明确学位规则。",
                    "is_critical": True,
                    "evidence_links": [
                        {
                            "evidence_id": "evidence.alpha.degree.coverage",
                            "support_scope": "coverage",
                            "citation_order": 1,
                        }
                    ],
                },
                {
                    "field_key": "taxonomy.low_altitude_basis",
                    "value_schema_version": "program_taxonomy_field.v1",
                    "value_payload": _taxonomy_payload(),
                    "display_text": "两门独立课程构成低空方向支撑。",
                    "is_critical": True,
                    "evidence_links": [
                        {
                            "evidence_id": "evidence.alpha.curriculum.one",
                            "support_scope": "direct",
                            "citation_order": 1,
                        },
                        {
                            "evidence_id": "evidence.alpha.curriculum.two",
                            "support_scope": "direct",
                            "citation_order": 2,
                        },
                    ],
                },
            ],
            "created_by": "actor.data_preparer.codex",
            "creation_note": "Phase 4 schema compatibility fixture.",
            "request_id": "request.phase4.schema.compatibility",
        }
    )


def test_registry_is_strict_complete_and_approved() -> None:
    registry = load_program_field_registry()
    assert len(registry.fields) == 16
    assert sum(item.presence == "required" for item in registry.fields) == 15
    assert sum(item.is_critical for item in registry.fields) == 11
    assert registry.definition_for("requirements.language").payload_schema_version == (
        "program_requirement_field.v2"
    )

    raw = registry.model_dump(mode="json")
    raw["fields"][0]["payload_schema_version"] = "program_taxonomy_field.v1"
    with pytest.raises(ValidationError, match="payload schema must match field kind"):
        ProgramFieldRegistry.model_validate(raw)


def test_new_field_payloads_accept_valid_values_and_reject_semantic_drift() -> None:
    TypeAdapter(ProgramCatalogFieldV1).validate_python(_catalog_payload())
    ProgramRequirementFieldV2.model_validate(_requirement_payload())
    TypeAdapter(ProgramTaxonomyFieldV1).validate_python(_taxonomy_payload())

    invalid_catalog = deepcopy(_catalog_payload())
    invalid_catalog["value"]["months"] = 0
    with pytest.raises(ValidationError):
        TypeAdapter(ProgramCatalogFieldV1).validate_python(invalid_catalog)

    invalid_requirement = deepcopy(_requirement_payload())
    invalid_requirement["requirements"][0]["requirement_type"] = "academic"
    with pytest.raises(ValidationError, match="requirement_type must match field_key"):
        ProgramRequirementFieldV2.model_validate(invalid_requirement)

    invalid_taxonomy = deepcopy(_taxonomy_payload())
    invalid_taxonomy["value"]["courses"][0]["course_type"] = "unknown"
    invalid_taxonomy["value"]["courses"][1]["course_type"] = "elective"
    with pytest.raises(ValidationError, match="core or required"):
        TypeAdapter(ProgramTaxonomyFieldV1).validate_python(invalid_taxonomy)


def test_candidate_union_fails_closed_for_registry_schema_and_criticality() -> None:
    valid = _candidate_payload()
    assert [field.value_schema_version for field in valid.fields] == [
        "program_catalog_field.v1",
        "program_requirement_field.v2",
        "program_requirement_field.v2",
        "program_taxonomy_field.v1",
    ]

    wrong_pair = valid.model_dump(mode="python")
    wrong_pair["fields"][0]["field_key"] = "catalog.department"
    with pytest.raises(ValidationError, match="field_key must match payload field_key"):
        CandidateCreate.model_validate(wrong_pair)

    wrong_criticality = valid.model_dump(mode="python")
    wrong_criticality["fields"][2]["is_critical"] = False
    with pytest.raises(ValidationError, match="criticality must match"):
        CandidateCreate.model_validate(wrong_criticality)

    wrong_evidence = valid.model_dump(mode="python")
    wrong_evidence["fields"][3]["evidence_links"].pop()
    with pytest.raises(ValidationError, match="payload evidence IDs must match"):
        CandidateCreate.model_validate(wrong_evidence)


def test_evidence_v1_and_v2_records_keep_distinct_response_shapes(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'evidence-v2.sqlite3'}"
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    with sessions.begin() as session:
        session.add(
            Program(
                id=PROGRAM_ID,
                official_name="Synthetic schema compatibility program",
                institution_name="Synthetic institution",
                region=ProgramRegion.UNITED_KINGDOM,
                official_program_url="https://study.ed.ac.uk/programmes/schema-test",
                registered_official_domain="ed.ac.uk",
                created_at=FIXED_NOW,
            )
        )

    v1_orm = phase3_support._evidence(
        "evidence.alpha.legacy", snapshot_sha256="a" * 64
    )
    v1 = SourceEvidenceCreate.model_validate(
        {column.name: getattr(v1_orm, column.name) for column in v1_orm.__table__.columns
         if column.name not in {"created_at", "capture_method", "hash_scope", "reviewed_source_role"}}
    )
    with sessions.begin() as session:
        repository = SourceEvidenceRepository(session, clock=lambda: FIXED_NOW)
        legacy = repository.create(v1)
        current = repository.create(_v2_evidence("evidence.alpha.current", "b"))

    legacy_json = legacy.model_dump(mode="json")
    current_json = current.model_dump(mode="json")
    assert "schema_version" not in legacy_json
    assert "capture_method" not in legacy_json
    assert current_json["schema_version"] == "source_evidence.v2"
    assert current_json["capture_method"] == "manual_browser"
    assert current_json["hash_scope"] == "normalized_excerpt"
    assert current_json["reviewed_source_role"] == "program"
    with pytest.raises(IntegrityError, match="invalid Evidence V2 metadata"):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE source_evidence SET hash_scope = NULL "
                    "WHERE id = 'evidence.alpha.current'"
                )
            )
    engine.dispose()


def test_evidence_v2_api_create_get_list_and_replay(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'evidence-v2-api.sqlite3'}"
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    with sessions.begin() as session:
        session.add(
            Program(
                id=PROGRAM_ID,
                official_name="Synthetic schema compatibility program",
                institution_name="Synthetic institution",
                region=ProgramRegion.UNITED_KINGDOM,
                official_program_url="https://study.ed.ac.uk/programmes/schema-test",
                registered_official_domain="ed.ac.uk",
                created_at=FIXED_NOW,
            )
        )
    app = create_app(
        Settings(_env_file=None, model_api_key=None),
        phase3_session_factory=sessions,
        phase3_clock=lambda: FIXED_NOW,
        phase3_id_factory=phase3_support.SequenceIds("phase4-evidence-api"),
    )
    payload = _v2_evidence("evidence.alpha.api", "c").model_dump(mode="json")
    headers = {"Idempotency-Key": "phase4-evidence-v2-api-key-0001"}
    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post(
            "/api/v1/internal/source-evidence", json=payload, headers=headers
        )
        replayed = client.post(
            "/api/v1/internal/source-evidence", json=payload, headers=headers
        )
        fetched = client.get(
            "/api/v1/internal/source-evidence/evidence.alpha.api"
        )
        listed = client.get(
            f"/api/v1/internal/programs/{PROGRAM_ID}/source-evidence"
        )
    assert created.status_code == 201
    assert replayed.status_code == 201
    assert replayed.json() == created.json()
    assert fetched.json() == created.json()
    assert listed.json()["evidence"] == [created.json()]
    assert created.json()["schema_version"] == "source_evidence.v2"
    engine.dispose()


def test_candidate_and_published_unions_round_trip_new_fields(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'field-unions.sqlite3'}"
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    with sessions.begin() as session:
        session.add(
            Program(
                id=PROGRAM_ID,
                official_name="Synthetic schema compatibility program",
                institution_name="Synthetic institution",
                region=ProgramRegion.UNITED_KINGDOM,
                official_program_url="https://study.ed.ac.uk/programmes/schema-test",
                registered_official_domain="ed.ac.uk",
                created_at=FIXED_NOW,
            )
        )
    evidence_ids = [
        "evidence.alpha.duration",
        "evidence.alpha.degree.coverage",
        "evidence.alpha.language",
        "evidence.alpha.curriculum.one",
        "evidence.alpha.curriculum.two",
    ]
    with sessions.begin() as session:
        repository = SourceEvidenceRepository(session, clock=lambda: FIXED_NOW)
        for index, evidence_id in enumerate(evidence_ids, start=1):
            repository.create(_v2_evidence(evidence_id, str(index)))
        candidate = CandidateRepository(
            session,
            clock=lambda: FIXED_NOW,
            id_factory=phase3_support.SequenceIds("phase4-union"),
        ).create(PROGRAM_ID, _candidate_payload())
        assert CandidateRepository(
            session,
            clock=lambda: FIXED_NOW,
            id_factory=lambda _kind: "unused",
        ).content_hash_is_valid(candidate.id)
        version = session.get(ProgramVersion, candidate.id)
        assert version is not None
        version.status = VersionStatus.PUBLISHED
        version.published_at = FIXED_NOW
        session.add(
            ProgramPublication(
                program_id=PROGRAM_ID,
                current_version_id=candidate.id,
                revision=1,
                updated_at=FIXED_NOW,
            )
        )

    with sessions.begin() as session:
        published = PublishedProgramReader(session, clock=lambda: FIXED_NOW).get(PROGRAM_ID)
    assert [field.value_schema_version for field in published.fields] == [
        "program_catalog_field.v1",
        "program_requirement_field.v2",
        "program_requirement_field.v2",
        "program_taxonomy_field.v1",
    ]
    degree_field = next(
        field for field in published.fields if field.field_key == "requirements.degree"
    )
    assert [citation.support_scope for citation in degree_field.evidence] == ["coverage"]
    assert all(
        citation.schema_version == "source_evidence.v2"
        for field in published.fields
        for citation in field.evidence
    )
    engine.dispose()


def _seed_phase3_pilot_database(database_url: str) -> dict[str, object]:
    upgrade_database(database_url, "20260901_0001")
    payload = phase3_support._candidate_payload().fields[0]
    field_hash = _value_hash(payload.value_payload)
    links = tuple(payload.evidence_links)
    field = _FieldSnapshot(
        id="field.phase3.compatibility",
        field_key=payload.field_key,
        value_schema_version=payload.value_schema_version,
        value_payload=payload.value_payload,
        display_text=payload.display_text,
        is_critical=payload.is_critical,
        value_sha256=field_hash,
        evidence_links=links,
    )
    evidence_sources = {
        phase3_support.E1: SimpleNamespace(snapshot_sha256="1" * 64),
        phase3_support.E2: SimpleNamespace(snapshot_sha256="2" * 64),
    }
    content_sha256 = content_hash(
        _content_envelope({payload.field_key: field}, evidence_sources)
    )
    value_payload = normalize(payload.value_payload)
    engine = create_database_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO programs (id, official_name, institution_name, region, "
                "official_program_url, registered_official_domain, created_at) "
                "VALUES (:id, :name, :institution, :region, :url, :domain, :created_at)"
            ),
            {
                "id": PROGRAM_ID,
                "name": "Computer Science MSc",
                "institution": "The University of Edinburgh",
                "region": "united_kingdom",
                "url": "https://study.ed.ac.uk/programmes/pilot",
                "domain": "ed.ac.uk",
                "created_at": FIXED_NOW,
            },
        )
        for evidence_id, character in (
            (phase3_support.E1, "1"),
            (phase3_support.E2, "2"),
        ):
            source = phase3_support._evidence(
                evidence_id, snapshot_sha256=character * 64
            )
            connection.execute(
                text(
                    "INSERT INTO source_evidence (id, program_id, source_type, url, "
                    "official_domain, page_title, excerpt, snapshot_sha256, source_version, "
                    "captured_at, verified_at, verified_by, review_due_at, expires_at, "
                    "availability_at_verification, created_at) VALUES "
                    "(:id, :program_id, :source_type, :url, :official_domain, :page_title, "
                    ":excerpt, :snapshot_sha256, :source_version, :captured_at, :verified_at, "
                    ":verified_by, :review_due_at, :expires_at, "
                    ":availability_at_verification, :created_at)"
                ),
                {
                    "id": source.id,
                    "program_id": source.program_id,
                    "source_type": source.source_type,
                    "url": source.url,
                    "official_domain": source.official_domain,
                    "page_title": source.page_title,
                    "excerpt": source.excerpt,
                    "snapshot_sha256": source.snapshot_sha256,
                    "source_version": source.source_version,
                    "captured_at": source.captured_at,
                    "verified_at": source.verified_at,
                    "verified_by": source.verified_by,
                    "review_due_at": source.review_due_at,
                    "expires_at": source.expires_at,
                    "availability_at_verification": source.availability_at_verification,
                    "created_at": FIXED_NOW,
                },
            )
        connection.execute(
            text(
                "INSERT INTO program_versions (id, program_id, version_no, base_version_id, "
                "rollback_of_version_id, status, content_schema_version, content_sha256, "
                "created_by, submitted_by, reviewed_by, review_note, created_at, submitted_at, "
                "reviewed_at, published_at) VALUES (:id, :program_id, 1, NULL, NULL, "
                "'published', 'program_version_content.v1', :content_sha256, :created_by, "
                ":submitted_by, :reviewed_by, :review_note, :created_at, :submitted_at, "
                ":reviewed_at, :published_at)"
            ),
            {
                "id": "version.phase3.compatibility",
                "program_id": PROGRAM_ID,
                "content_sha256": content_sha256,
                "created_by": "actor.data_preparer.codex",
                "submitted_by": "actor.data_preparer.codex",
                "reviewed_by": "actor.domain_reviewer.product_owner",
                "review_note": "Phase 3 accepted compatibility fixture.",
                "created_at": FIXED_NOW,
                "submitted_at": FIXED_NOW,
                "reviewed_at": FIXED_NOW,
                "published_at": FIXED_NOW,
            },
        )
        connection.execute(
            text(
                "INSERT INTO program_field_values (id, program_version_id, field_key, "
                "value_schema_version, value_payload, display_text, is_critical, value_sha256) "
                "VALUES (:id, :version_id, :field_key, :schema_version, :value_payload, "
                ":display_text, 1, :value_sha256)"
            ),
            {
                "id": field.id,
                "version_id": "version.phase3.compatibility",
                "field_key": field.field_key,
                "schema_version": field.value_schema_version,
                "value_payload": json.dumps(value_payload, ensure_ascii=False),
                "display_text": field.display_text,
                "value_sha256": field_hash,
            },
        )
        for link in links:
            connection.execute(
                text(
                    "INSERT INTO field_evidence_links (field_value_id, evidence_id, "
                    "support_scope, citation_order) VALUES (:field_id, :evidence_id, "
                    ":support_scope, :citation_order)"
                ),
                {
                    "field_id": field.id,
                    "evidence_id": link.evidence_id,
                    "support_scope": link.support_scope.value,
                    "citation_order": link.citation_order,
                },
            )
        connection.execute(
            text(
                "INSERT INTO program_publications (program_id, current_version_id, revision, "
                "updated_at) VALUES (:program_id, :version_id, 1, :updated_at)"
            ),
            {
                "program_id": PROGRAM_ID,
                "version_id": "version.phase3.compatibility",
                "updated_at": FIXED_NOW,
            },
        )
    engine.dispose()
    return {
        "value_payload": value_payload,
        "field_sha256": field_hash,
        "content_sha256": content_sha256,
        "evidence_sha256": {
            phase3_support.E1: "1" * 64,
            phase3_support.E2: "2" * 64,
        },
    }


def test_phase3_database_upgrade_preserves_pilot_json_and_all_hashes(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'phase3-upgrade.sqlite3'}"
    before = _seed_phase3_pilot_database(database_url)
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)

    evidence_columns = {
        column["name"] for column in inspect(engine).get_columns("source_evidence")
    }
    program_columns = {
        column["name"] for column in inspect(engine).get_columns("programs")
    }
    assert {"capture_method", "hash_scope", "reviewed_source_role"}.issubset(
        evidence_columns
    )
    assert "official_domain_aliases" in program_columns
    with engine.connect() as connection:
        stored_field = connection.execute(
            text(
                "SELECT value_payload, value_sha256 FROM program_field_values "
                "WHERE id = 'field.phase3.compatibility'"
            )
        ).mappings().one()
        stored_content = connection.execute(
            text(
                "SELECT content_sha256 FROM program_versions "
                "WHERE id = 'version.phase3.compatibility'"
            )
        ).scalar_one()
        stored_evidence = dict(
            connection.execute(
                text(
                    "SELECT id, snapshot_sha256 FROM source_evidence ORDER BY id"
                )
            ).all()
        )
        v2_metadata = connection.execute(
            text(
                "SELECT capture_method, hash_scope, reviewed_source_role "
                "FROM source_evidence ORDER BY id"
            )
        ).all()
        official_domain_aliases = connection.execute(
            text(
                "SELECT official_domain_aliases FROM programs "
                "WHERE id = :program_id"
            ),
            {"program_id": PROGRAM_ID},
        ).scalar_one()

    with sessions.begin() as session:
        published = PublishedProgramReader(session, clock=lambda: FIXED_NOW).get(PROGRAM_ID)
    public_json = published.model_dump(mode="json")
    assert json.loads(stored_field["value_payload"]) == before["value_payload"]
    assert stored_field["value_sha256"] == before["field_sha256"]
    assert stored_content == before["content_sha256"]
    assert stored_evidence == before["evidence_sha256"]
    assert all(row == (None, None, None) for row in v2_metadata)
    assert json.loads(official_domain_aliases) == []
    assert public_json["content_sha256"] == before["content_sha256"]
    assert public_json["fields"][0]["value_sha256"] == before["field_sha256"]
    assert public_json["fields"][0]["value_payload"] == before["value_payload"]
    assert all("schema_version" not in item for item in public_json["fields"][0]["evidence"])
    assert all("capture_method" not in item for item in public_json["fields"][0]["evidence"])
    engine.dispose()


def test_empty_database_upgrade_and_constraints_accept_coverage(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'empty-head.sqlite3'}"
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    assert {table for table in inspect(engine).get_table_names()} >= {
        "source_evidence",
        "field_evidence_links",
    }
    engine.dispose()
