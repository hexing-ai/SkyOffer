from __future__ import annotations

import ast
import hashlib
import inspect
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import backend.tests.test_phase4_program_pack_contract as pack_support
from backend.app.core.config import Settings
from backend.app.db.migrations import upgrade_database
from backend.app.db.models import (
    AuditEvent,
    EvidenceAvailability,
    FieldEvidenceLink,
    IdempotencyRecord,
    Program,
    ProgramFieldValue,
    ProgramPublication,
    ProgramVersion,
    SourceEvidence,
    SourceType,
    VersionStatus,
)
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.main import create_app
from backend.app.repositories.candidates import CandidateRepository
from backend.app.repositories.idempotency import IdempotencyConflictError
from backend.app.schemas.alpha_manifest import AlphaScopeSnapshotV1
from backend.app.schemas.alpha_program_pack import AlphaProgramPackV1
from backend.app.schemas.candidates import CandidateCreate
from backend.app.schemas.version_workflow import (
    PublishVersionCommand,
    SubmitVersionCommand,
)
from backend.app.services.alpha_candidate_importer import (
    AlphaCandidateBatchImporter,
    AlphaCandidateImportCommand,
    AlphaCandidateImporter,
    AlphaImportedContentMismatchError,
)
from backend.app.services.alpha_program_pack_validator import (
    AlphaProgramPackValidationError,
    alpha_program_pack_hash,
    alpha_program_pack_semantic_hash,
)
from backend.app.services.version_workflow import VersionWorkflowService


FIXED_NOW = datetime(2026, 9, 2, 4, 0, tzinfo=timezone.utc)
IMPORT_KEY = "alpha-pack-import-key-0001"


class SequenceIds:
    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self.counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        count = self.counts.get(kind, 0) + 1
        self.counts[kind] = count
        return f"{kind}.{self.namespace}.{count}"


@pytest.fixture
def importer_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'alpha-importer.sqlite3'}"
    upgrade_database(url)
    engine = create_database_engine(url)
    sessions = create_session_factory(engine)
    yield url, engine, sessions
    engine.dispose()


def _scope() -> AlphaScopeSnapshotV1:
    return AlphaScopeSnapshotV1.model_validate(pack_support._frozen_scope_raw())


def _pack() -> AlphaProgramPackV1:
    return AlphaProgramPackV1.model_validate(pack_support._signed_pack_raw())


def _resign(raw: dict) -> AlphaProgramPackV1:
    raw["pack_canonical_sha256"] = "0" * 64
    raw["expected_semantic_content_sha256"] = "0" * 64
    pack = AlphaProgramPackV1.model_validate(raw)
    raw["expected_semantic_content_sha256"] = alpha_program_pack_semantic_hash(
        pack
    )
    pack = AlphaProgramPackV1.model_validate(raw)
    raw["pack_canonical_sha256"] = alpha_program_pack_hash(pack)
    return AlphaProgramPackV1.model_validate(raw)


def _replace_strings(value, replacements: dict[str, str]):
    if isinstance(value, str):
        result = value
        for before, after in replacements.items():
            result = result.replace(before, after)
        return result
    if isinstance(value, list):
        return [_replace_strings(item, replacements) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_strings(item, replacements)
            for key, item in value.items()
        }
    return value


def _second_program_pack() -> AlphaProgramPackV1:
    raw = _replace_strings(
        deepcopy(pack_support._signed_pack_raw()),
        {
            "pack.synthetic.cs.01": "pack.synthetic.cs.02",
            "program.synthetic.cs.01": "program.synthetic.cs.02",
            "institution.synthetic.hk.01": "institution.synthetic.hk.02",
            "Synthetic Hong Kong Institution 01": (
                "Synthetic Hong Kong Institution 02"
            ),
            "Synthetic MSc Computer Science": "Synthetic MSc Computing Two",
            "evidence.synthetic.program": "evidence.synthetic.program.02",
            "request.synthetic.pack.01": "request.synthetic.pack.02",
            "hk1.example.edu.hk": "hk2.example.edu.hk",
        },
    )
    return _resign(raw)


def _counts(session) -> dict[str, int]:
    models = {
        "programs": Program,
        "evidence": SourceEvidence,
        "versions": ProgramVersion,
        "fields": ProgramFieldValue,
        "links": FieldEvidenceLink,
        "audits": AuditEvent,
        "idempotency": IdempotencyRecord,
        "publications": ProgramPublication,
    }
    return {
        name: int(session.scalar(select(func.count()).select_from(model)) or 0)
        for name, model in models.items()
    }


def _import(session, ids: SequenceIds, pack: AlphaProgramPackV1, key: str):
    return AlphaCandidateImporter(
        session, clock=lambda: FIXED_NOW, id_factory=ids
    ).import_pack(pack=pack, scope=_scope(), idempotency_key=key)


def _public_client(sessions, ids: SequenceIds) -> TestClient:
    return TestClient(
        create_app(
            Settings(_env_file=None, model_api_key=None),
            phase3_session_factory=sessions,
            phase3_clock=lambda: FIXED_NOW,
            phase3_id_factory=ids,
        ),
        raise_server_exceptions=False,
    )


def _legacy_candidate() -> CandidateCreate:
    display = "2026–27 IELTS Academic: total 7.0, each component 6.5."
    evidence_ids = [
        "evidence.synthetic.legacy.direct",
        "evidence.synthetic.legacy.policy",
    ]
    return CandidateCreate.model_validate(
        {
            "base_version_id": None,
            "fields": [
                {
                    "field_key": "requirements.language.ielts",
                    "value_schema_version": "program_requirement_field.v1",
                    "value_payload": {
                        "schema_version": "program_requirement_field.v1",
                        "applicable_academic_year": "2026-27",
                        "coverage": "score_threshold_only",
                        "requirement": {
                            "requirement_id": "requirement.synthetic.legacy.ielts",
                            "requirement_type": "language",
                            "is_hard": True,
                            "applicability": None,
                            "rule": {
                                "node_id": "node.synthetic.legacy.ielts",
                                "operator": "language_minimum",
                                "test_type": "ielts",
                                "total_min": "7.0",
                                "component_mins": {
                                    "listening": "6.5",
                                    "reading": "6.5",
                                    "speaking": "6.5",
                                    "writing": "6.5",
                                },
                            },
                            "evidence_fixture_ids": evidence_ids,
                            "display_text": display,
                        },
                    },
                    "display_text": display,
                    "is_critical": True,
                    "evidence_links": [
                        {
                            "evidence_id": evidence_ids[0],
                            "support_scope": "direct",
                            "citation_order": 1,
                        },
                        {
                            "evidence_id": evidence_ids[1],
                            "support_scope": "definition",
                            "citation_order": 2,
                        },
                    ],
                }
            ],
            "created_by": "actor.data_preparer.codex",
            "creation_note": "Synthetic legacy v1 candidate.",
            "request_id": "request.synthetic.legacy.candidate",
        }
    )


def test_valid_pack_imports_only_program_evidence_and_candidate_idempotently(
    importer_database,
) -> None:
    _, _, sessions = importer_database
    ids = SequenceIds("alpha-first")
    pack = _pack()
    with sessions.begin() as session:
        first = _import(session, ids, pack, IMPORT_KEY)
        replay = _import(session, ids, pack, IMPORT_KEY)
        assert replay == first
        assert first.program_id == pack.program.program_ref
        assert first.program_created is True
        assert first.candidate_status == "candidate"
        assert first.candidate_content_sha256 == (
            pack.expected_semantic_content_sha256
        )
        assert first.publication_current_version_id is None

    with sessions.begin() as session:
        assert _counts(session) == {
            "programs": 1,
            "evidence": 1,
            "versions": 1,
            "fields": 15,
            "links": 15,
            "audits": 2,
            "idempotency": 1,
            "publications": 0,
        }
        version = session.get(ProgramVersion, first.candidate_version_id)
        assert version is not None
        assert version.status == VersionStatus.CANDIDATE
        assert version.submitted_at is None
        assert version.reviewed_at is None
        assert version.published_at is None
        audits = session.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
        expected_key_hash = hashlib.sha256(IMPORT_KEY.encode("utf-8")).hexdigest()
        assert {audit.idempotency_key_hash for audit in audits} == {
            expected_key_hash
        }

    with _public_client(sessions, ids) as client:
        response = client.get(
            f"/api/v1/programs/{pack.program.program_ref}/published"
        )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROGRAM_NOT_PUBLISHED"


def test_same_key_with_different_frozen_pack_is_an_idempotency_conflict(
    importer_database,
) -> None:
    _, _, sessions = importer_database
    ids = SequenceIds("alpha-conflict")
    first_pack = _pack()
    changed_raw = deepcopy(pack_support._signed_pack_raw())
    changed_raw["pack_ref"] = "pack.synthetic.cs.01.repacked"
    changed_pack = _resign(changed_raw)

    with sessions.begin() as session:
        _import(session, ids, first_pack, IMPORT_KEY)
    with sessions.begin() as session:
        with pytest.raises(IdempotencyConflictError):
            _import(session, ids, changed_pack, IMPORT_KEY)

    with sessions.begin() as session:
        assert _counts(session)["versions"] == 1
        assert _counts(session)["idempotency"] == 1


def test_failure_after_candidate_creation_rolls_back_everything_and_can_retry(
    importer_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, sessions = importer_database
    ids = SequenceIds("alpha-rollback")
    original_create = CandidateRepository.create

    def create_then_fail(repository, program_id, payload):
        original_create(repository, program_id, payload)
        raise RuntimeError("injected failure after candidate creation")

    monkeypatch.setattr(CandidateRepository, "create", create_then_fail)
    with sessions() as session:
        with pytest.raises(RuntimeError, match="injected failure"):
            _import(session, ids, _pack(), IMPORT_KEY)
        session.commit()

    with sessions.begin() as session:
        assert all(count == 0 for count in _counts(session).values())

    monkeypatch.undo()
    with sessions.begin() as session:
        result = _import(session, ids, _pack(), IMPORT_KEY)
        assert result.candidate_status == "candidate"
    with sessions.begin() as session:
        assert _counts(session)["versions"] == 1
        assert _counts(session)["idempotency"] == 1


def test_repository_semantic_mismatch_rolls_back_the_complete_import(
    importer_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, sessions = importer_database
    ids = SequenceIds("alpha-semantic-mismatch")
    original_create = CandidateRepository.create

    def create_with_wrong_reported_hash(repository, program_id, payload):
        created = original_create(repository, program_id, payload)
        return created.model_copy(update={"content_sha256": "f" * 64})

    monkeypatch.setattr(
        CandidateRepository, "create", create_with_wrong_reported_hash
    )
    with sessions() as session:
        with pytest.raises(
            AlphaImportedContentMismatchError, match="semantic hash"
        ):
            _import(session, ids, _pack(), IMPORT_KEY)
        session.commit()
    with sessions.begin() as session:
        assert all(count == 0 for count in _counts(session).values())


def test_invalid_pack_is_rejected_before_idempotency_or_database_writes(
    importer_database,
) -> None:
    _, _, sessions = importer_database
    ids = SequenceIds("alpha-invalid")
    raw = deepcopy(pack_support._signed_pack_raw())
    raw["pack_canonical_sha256"] = "f" * 64
    invalid_pack = AlphaProgramPackV1.model_validate(raw)

    with sessions() as session:
        with pytest.raises(
            AlphaProgramPackValidationError, match="stored pack canonical hash"
        ):
            _import(session, ids, invalid_pack, IMPORT_KEY)
        session.commit()
    with sessions.begin() as session:
        assert all(count == 0 for count in _counts(session).values())


def test_new_candidate_does_not_replace_an_existing_published_version(
    importer_database,
) -> None:
    _, _, sessions = importer_database
    ids = SequenceIds("alpha-published")
    alpha_pack = _pack()
    with sessions.begin() as session:
        session.add(
            Program(
                id=alpha_pack.program.program_ref,
                official_name=alpha_pack.program.official_name,
                institution_name=alpha_pack.program.institution_name,
                region=alpha_pack.program.region,
                official_program_url=alpha_pack.program.official_program_url,
                registered_official_domain=(
                    alpha_pack.program.registered_official_domain
                ),
                created_at=FIXED_NOW,
            )
        )
        review_due = FIXED_NOW + timedelta(days=30)
        for evidence_id, suffix, hash_character in (
            ("evidence.synthetic.legacy.direct", "direct", "d"),
            ("evidence.synthetic.legacy.policy", "policy", "e"),
        ):
            session.add(
                SourceEvidence(
                    id=evidence_id,
                    program_id=alpha_pack.program.program_ref,
                    source_type=SourceType.OFFICIAL_PROGRAM_PAGE,
                    url=f"https://www.hk1.example.edu.hk/legacy-{suffix}",
                    official_domain="www.hk1.example.edu.hk",
                    page_title=f"Synthetic legacy {suffix}",
                    excerpt=f"Synthetic verified legacy {suffix} excerpt.",
                    snapshot_sha256=hash_character * 64,
                    source_version="synthetic legacy 2026-27 fixture",
                    captured_at=FIXED_NOW,
                    verified_at=FIXED_NOW,
                    verified_by="actor.domain_reviewer.product_owner",
                    review_due_at=review_due,
                    expires_at=review_due + timedelta(days=30),
                    availability_at_verification=EvidenceAvailability.AVAILABLE,
                    created_at=FIXED_NOW,
                )
            )
        legacy = CandidateRepository(
            session, clock=lambda: FIXED_NOW, id_factory=ids
        ).create(alpha_pack.program.program_ref, _legacy_candidate())
        workflow = VersionWorkflowService(
            session, clock=lambda: FIXED_NOW, id_factory=ids
        )
        workflow.submit(
            legacy.id,
            SubmitVersionCommand(
                submitted_by="actor.data_preparer.codex",
                submission_note="Explicit test submit outside the importer.",
                request_id="request.synthetic.submit.v1",
            ),
        )
        workflow.publish(
            legacy.id,
            PublishVersionCommand(
                reviewed_by="actor.domain_reviewer.product_owner",
                review_note="Explicit test publish outside the importer.",
                request_id="request.synthetic.publish.v1",
                expected_current_version_id=None,
            ),
        )

    with _public_client(sessions, ids) as client:
        published_before = client.get(
            f"/api/v1/programs/{alpha_pack.program.program_ref}/published"
        )
    assert published_before.status_code == 200
    assert published_before.json()["fields"][0]["value_schema_version"] == (
        "program_requirement_field.v1"
    )

    with sessions.begin() as session:
        second = _import(
            session,
            ids,
            alpha_pack,
            "alpha-pack-import-key-0002",
        )
        assert second.program_created is False
        assert second.candidate_status == "candidate"
        assert second.candidate_version_no == 2
        assert second.publication_current_version_id == legacy.id
        version = session.get(ProgramVersion, second.candidate_version_id)
        assert version is not None
        assert version.base_version_id == legacy.id

    with _public_client(sessions, ids) as client:
        published_after = client.get(
            f"/api/v1/programs/{alpha_pack.program.program_ref}/published"
        )
    assert published_after.status_code == 200
    assert published_after.json() == published_before.json()
    with sessions.begin() as session:
        pointer = session.get(ProgramPublication, alpha_pack.program.program_ref)
        assert pointer is not None
        assert pointer.current_version_id == legacy.id
        statuses = session.scalars(
            select(ProgramVersion.status).order_by(ProgramVersion.version_no)
        ).all()
        assert statuses == [VersionStatus.PUBLISHED, VersionStatus.CANDIDATE]


def test_batch_report_keeps_success_and_reports_failed_pack_separately(
    importer_database,
) -> None:
    _, _, sessions = importer_database
    ids = SequenceIds("alpha-batch")
    invalid_raw = _second_program_pack().model_dump(mode="python")
    invalid_raw["pack_canonical_sha256"] = "f" * 64
    invalid_pack = AlphaProgramPackV1.model_validate(invalid_raw)
    report = AlphaCandidateBatchImporter(
        sessions,
        clock=lambda: FIXED_NOW,
        id_factory=ids,
    ).import_commands(
        [
            AlphaCandidateImportCommand(
                pack=_pack(),
                scope=_scope(),
                idempotency_key="alpha-batch-import-key-0001",
            ),
            AlphaCandidateImportCommand(
                pack=invalid_pack,
                scope=_scope(),
                idempotency_key="alpha-batch-import-key-0002",
            ),
        ]
    )
    assert report.attempted_count == 2
    assert report.imported_count == 1
    assert report.failed_count == 1
    assert report.complete is False
    assert [item.status for item in report.items] == ["imported", "failed"]
    assert report.items[1].error_code == "ALPHA_IMPORT_FAILED"
    assert "excerpt" not in (report.items[1].error_message or "")

    with sessions.begin() as session:
        assert _counts(session)["programs"] == 1
        assert session.get(Program, _pack().program.program_ref) is not None
        assert session.get(Program, invalid_pack.program.program_ref) is None


def test_importer_has_no_workflow_transition_call_path() -> None:
    tree = ast.parse(inspect.getsource(AlphaCandidateImporter))
    called_names = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    assert called_names.isdisjoint(
        {"submit", "publish", "reject", "rollback", "create_rollback"}
    )
