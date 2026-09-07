from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from backend.app.db.migrations import upgrade_database
from backend.app.db.models import (
    AuditEvent,
    AuditEventType,
    EvidenceAvailability,
    EvidenceSupportScope,
    FieldEvidenceLink,
    Program,
    ProgramFieldValue,
    ProgramPublication,
    ProgramRegion,
    ProgramVersion,
    SourceEvidence,
    SourceType,
    VersionStatus,
)
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.repositories.candidates import (
    CandidateEvidenceNotFoundError,
    CandidateEvidenceProgramMismatchError,
    CandidateImmutableError,
    CandidateRepository,
)
from backend.app.schemas.candidates import CandidateCreate


PROGRAM_ID = "program.pilot.edinburgh.computer_science_msc"
OTHER_PROGRAM_ID = "program.pilot.other.computer_science_msc"
E1 = "evidence.pilot.edinburgh.cs.ielts.2026_27"
E2 = "evidence.pilot.edinburgh.english_policy.2026"
E3 = "evidence.pilot.edinburgh.cs.2027_28.pending"
CROSS_EVIDENCE = "evidence.pilot.other.ielts"
FIXED_NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


class SequenceIds:
    def __init__(self, namespace: str = "test") -> None:
        self.namespace = namespace
        self.counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        next_value = self.counts.get(kind, 0) + 1
        self.counts[kind] = next_value
        return f"{kind}.{self.namespace}.{next_value}"


def _evidence(
    evidence_id: str,
    *,
    program_id: str = PROGRAM_ID,
    snapshot_sha256: str,
) -> SourceEvidence:
    review_due = FIXED_NOW + timedelta(days=30)
    return SourceEvidence(
        id=evidence_id,
        program_id=program_id,
        source_type=SourceType.OFFICIAL_PROGRAM_PAGE,
        url=f"https://study.ed.ac.uk/pilot/{evidence_id}",
        official_domain="study.ed.ac.uk",
        page_title=f"Pilot source {evidence_id}",
        excerpt=f"Verified pilot excerpt for {evidence_id}",
        snapshot_sha256=snapshot_sha256,
        source_version="pilot fixture observed 2026-09-01",
        captured_at=FIXED_NOW,
        verified_at=FIXED_NOW,
        verified_by="actor.domain_reviewer.product_owner",
        review_due_at=review_due,
        expires_at=review_due + timedelta(days=7),
        availability_at_verification=EvidenceAvailability.AVAILABLE,
        created_at=FIXED_NOW,
    )


@pytest.fixture
def candidate_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'candidates.sqlite3'}"
    upgrade_database(url)
    engine = create_database_engine(url)
    sessions = create_session_factory(engine)
    with sessions.begin() as session:
        session.add_all(
            [
                Program(
                    id=PROGRAM_ID,
                    official_name="Computer Science MSc",
                    institution_name="The University of Edinburgh",
                    region=ProgramRegion.UNITED_KINGDOM,
                    official_program_url=(
                        "https://study.ed.ac.uk/programmes/postgraduate-taught/"
                        "110-computer-science"
                    ),
                    registered_official_domain="ed.ac.uk",
                    created_at=FIXED_NOW,
                ),
                Program(
                    id=OTHER_PROGRAM_ID,
                    official_name="Other Computer Science MSc",
                    institution_name="Other Pilot University",
                    region=ProgramRegion.UNITED_KINGDOM,
                    official_program_url="https://example.ac.uk/programmes/computer-science",
                    registered_official_domain="example.ac.uk",
                    created_at=FIXED_NOW,
                ),
                _evidence(E1, snapshot_sha256="1" * 64),
                _evidence(E2, snapshot_sha256="2" * 64),
                _evidence(E3, snapshot_sha256="3" * 64),
                _evidence(
                    CROSS_EVIDENCE,
                    program_id=OTHER_PROGRAM_ID,
                    snapshot_sha256="4" * 64,
                ),
            ]
        )
    yield url, engine, sessions
    engine.dispose()


def _candidate_payload(
    *,
    direct_evidence: str = E1,
    policy_evidence: str = E2,
    base_version_id: str | None = None,
    academic_year: str = "2026-27",
    manual_review: bool = False,
    display_text: str | None = None,
    created_by: str = "actor.data_preparer.codex",
    request_id: str = "request.candidate.create",
    direct_scope: str = "direct",
    reverse_components: bool = False,
    reverse_citations: bool = False,
) -> CandidateCreate:
    evidence_ids = [direct_evidence, policy_evidence]
    if manual_review:
        rule = {
            "node_id": "node.pilot.ielts.manual_review",
            "operator": "manual_review",
            "reason_code": "OFFICIAL_RULE_AMBIGUOUS",
        }
        default_text = "2027–28 IELTS 要求尚未形成无歧义官方规则，需人工复核。"
    else:
        components = [
            ("listening", "6.50"),
            ("reading", "6.5"),
            ("speaking", "6.500"),
            ("writing", "6.5"),
        ]
        if reverse_components:
            components.reverse()
        rule = {
            "node_id": "node.pilot.ielts.minimum",
            "operator": "language_minimum",
            "test_type": "ielts",
            "total_min": "7.00",
            "component_mins": dict(components),
        }
        default_text = "2026–27 IELTS Academic：总分至少 7.0，各项至少 6.5。"
    final_display = display_text or default_text
    links = [
        {
            "evidence_id": direct_evidence,
            "support_scope": direct_scope,
            "citation_order": 1,
        },
        {
            "evidence_id": policy_evidence,
            "support_scope": "definition",
            "citation_order": 2,
        },
    ]
    if reverse_citations:
        links[0]["citation_order"] = 2
        links[1]["citation_order"] = 1
        links.reverse()
    return CandidateCreate.model_validate(
        {
            "base_version_id": base_version_id,
            "fields": [
                {
                    "field_key": "requirements.language.ielts",
                    "value_schema_version": "program_requirement_field.v1",
                    "value_payload": {
                        "schema_version": "program_requirement_field.v1",
                        "applicable_academic_year": academic_year,
                        "coverage": "score_threshold_only",
                        "requirement": {
                            "requirement_id": "requirement.pilot.ielts",
                            "requirement_type": "language",
                            "is_hard": True,
                            "applicability": None,
                            "rule": rule,
                            "evidence_fixture_ids": evidence_ids,
                            "display_text": final_display,
                        },
                    },
                    "display_text": final_display,
                    "is_critical": True,
                    "evidence_links": links,
                }
            ],
            "created_by": created_by,
            "creation_note": "Create immutable candidate snapshot for review.",
            "request_id": request_id,
        }
    )


def _publish_for_test(session, candidate) -> None:
    version = session.get(ProgramVersion, candidate.id)
    assert version is not None
    version.status = VersionStatus.PUBLISHED
    session.add(
        ProgramPublication(
            program_id=PROGRAM_ID,
            current_version_id=candidate.id,
            revision=1,
            updated_at=FIXED_NOW,
        )
    )
    session.flush()


def test_candidate_schema_is_strict_and_rejects_client_diff() -> None:
    raw = _candidate_payload().model_dump(mode="python")
    raw["diff"] = [{"change_type": "unchanged"}]
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CandidateCreate.model_validate(raw)

    raw = _candidate_payload().model_dump(mode="python")
    raw["fields"][0]["value_payload"]["unknown_fact"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CandidateCreate.model_validate(raw)

    raw = _candidate_payload().model_dump(mode="python")
    raw["fields"][0]["field_key"] = "requirements.language.toefl"
    with pytest.raises(ValidationError):
        CandidateCreate.model_validate(raw)


def test_first_candidate_is_an_atomic_snapshot_with_server_added_diff(
    candidate_database,
) -> None:
    _, _, sessions = candidate_database
    ids = SequenceIds("first")
    with sessions.begin() as session:
        created = CandidateRepository(
            session, clock=lambda: FIXED_NOW, id_factory=ids
        ).create(PROGRAM_ID, _candidate_payload())

        assert created.version_no == 1
        assert created.status == VersionStatus.CANDIDATE
        assert created.created_at == FIXED_NOW
        assert len(created.fields) == 1
        assert created.diff[0].change_type == "added"
        assert created.diff[0].before is None
        assert created.diff[0].after is not None
        assert created.diff[0].evidence_added == [E1, E2]
        assert len(created.content_sha256) == 64
        assert len(created.fields[0].value_sha256) == 64

        assert session.scalar(select(func.count()).select_from(ProgramVersion)) == 1
        assert session.scalar(select(func.count()).select_from(ProgramFieldValue)) == 1
        assert session.scalar(select(func.count()).select_from(FieldEvidenceLink)) == 2
        audit = session.scalar(select(AuditEvent))
        assert audit is not None
        assert audit.event_type == AuditEventType.CREATE
        assert audit.version_id == created.id
        assert audit.event_payload["content_sha256"] == created.content_sha256


def test_equivalent_facts_ignore_order_display_actor_time_and_database_ids(
    candidate_database,
) -> None:
    _, _, sessions = candidate_database
    ids = SequenceIds("stable")
    with sessions.begin() as session:
        first = CandidateRepository(
            session, clock=lambda: FIXED_NOW, id_factory=ids
        ).create(PROGRAM_ID, _candidate_payload())
        second = CandidateRepository(
            session,
            clock=lambda: FIXED_NOW + timedelta(hours=4),
            id_factory=ids,
        ).create(
            PROGRAM_ID,
            _candidate_payload(
                display_text="同一结构化门槛事实的另一种人工展示文本。",
                created_by="actor.data_preparer.second",
                request_id="request.candidate.second",
                reverse_components=True,
                reverse_citations=True,
            ),
        )

    assert first.id != second.id
    assert first.version_no != second.version_no
    assert first.created_at != second.created_at
    assert first.fields[0].id != second.fields[0].id
    assert first.fields[0].display_text != second.fields[0].display_text
    assert first.fields[0].value_sha256 == second.fields[0].value_sha256
    assert first.content_sha256 == second.content_sha256


def test_payload_evidence_and_support_scope_changes_affect_expected_hashes(
    candidate_database,
) -> None:
    _, _, sessions = candidate_database
    ids = SequenceIds("changes")
    with sessions.begin() as session:
        repository = CandidateRepository(
            session, clock=lambda: FIXED_NOW, id_factory=ids
        )
        original = repository.create(PROGRAM_ID, _candidate_payload())
        changed_scope = repository.create(
            PROGRAM_ID, _candidate_payload(direct_scope="applicability")
        )
        changed_evidence = repository.create(
            PROGRAM_ID, _candidate_payload(direct_evidence=E3)
        )
        changed_payload = repository.create(
            PROGRAM_ID,
            _candidate_payload(
                academic_year="2027-28",
                manual_review=True,
                direct_evidence=E3,
            ),
        )

    assert original.fields[0].value_sha256 == changed_scope.fields[0].value_sha256
    assert original.content_sha256 != changed_scope.content_sha256
    assert original.fields[0].value_sha256 == changed_evidence.fields[0].value_sha256
    assert original.content_sha256 != changed_evidence.content_sha256
    assert original.fields[0].value_sha256 != changed_payload.fields[0].value_sha256
    assert original.content_sha256 != changed_payload.content_sha256


def test_snapshot_hash_is_part_of_content_hash(tmp_path) -> None:
    hashes: list[str] = []
    for index, snapshot_hash in enumerate(("a" * 64, "b" * 64), start=1):
        url = f"sqlite:///{tmp_path / f'snapshot-{index}.sqlite3'}"
        upgrade_database(url)
        engine = create_database_engine(url)
        sessions = create_session_factory(engine)
        with sessions.begin() as session:
            session.add(
                Program(
                    id=PROGRAM_ID,
                    official_name="Computer Science MSc",
                    institution_name="The University of Edinburgh",
                    region=ProgramRegion.UNITED_KINGDOM,
                    official_program_url="https://study.ed.ac.uk/programmes/pilot",
                    registered_official_domain="ed.ac.uk",
                    created_at=FIXED_NOW,
                )
            )
            session.add_all(
                [
                    _evidence(E1, snapshot_sha256=snapshot_hash),
                    _evidence(E2, snapshot_sha256="2" * 64),
                ]
            )
        with sessions.begin() as session:
            candidate = CandidateRepository(
                session,
                clock=lambda: FIXED_NOW,
                id_factory=SequenceIds(f"snapshot{index}"),
            ).create(PROGRAM_ID, _candidate_payload())
            hashes.append(candidate.content_sha256)
        engine.dispose()

    assert hashes[0] != hashes[1]


def test_changed_candidate_diff_uses_published_base_and_evidence_identity(
    candidate_database,
) -> None:
    _, _, sessions = candidate_database
    ids = SequenceIds("diff")
    with sessions.begin() as session:
        repository = CandidateRepository(
            session, clock=lambda: FIXED_NOW, id_factory=ids
        )
        v1 = repository.create(PROGRAM_ID, _candidate_payload())
        _publish_for_test(session, v1)

    with sessions.begin() as session:
        v2 = CandidateRepository(
            session,
            clock=lambda: FIXED_NOW + timedelta(days=1),
            id_factory=ids,
        ).create(
            PROGRAM_ID,
            _candidate_payload(
                base_version_id=v1.id,
                academic_year="2027-28",
                manual_review=True,
                direct_evidence=E3,
                request_id="request.candidate.v2",
            ),
        )

    assert v2.version_no == 2
    assert v2.base_version_id == v1.id
    assert len(v2.diff) == 1
    change = v2.diff[0]
    assert change.change_type == "changed"
    assert change.before is not None and change.after is not None
    assert change.before.value_sha256 == v1.fields[0].value_sha256
    assert change.after.value_sha256 == v2.fields[0].value_sha256
    assert change.evidence_removed == [E1]
    assert change.evidence_added == [E3]
    assert E2 not in change.evidence_removed
    assert E2 not in change.evidence_added


def test_empty_atomic_snapshot_reports_removed_field(candidate_database) -> None:
    _, _, sessions = candidate_database
    ids = SequenceIds("removed")
    with sessions.begin() as session:
        repository = CandidateRepository(
            session, clock=lambda: FIXED_NOW, id_factory=ids
        )
        v1 = repository.create(PROGRAM_ID, _candidate_payload())
        _publish_for_test(session, v1)

    empty_payload = CandidateCreate.model_validate(
        {
            "base_version_id": v1.id,
            "fields": [],
            "created_by": "actor.data_preparer.codex",
            "creation_note": "Remove the pilot field in a new complete snapshot.",
            "request_id": "request.candidate.removed",
        }
    )
    with sessions.begin() as session:
        removed = CandidateRepository(
            session,
            clock=lambda: FIXED_NOW + timedelta(days=1),
            id_factory=ids,
        ).create(PROGRAM_ID, empty_payload)

    assert removed.fields == []
    assert len(removed.diff) == 1
    assert removed.diff[0].change_type == "removed"
    assert removed.diff[0].before is not None
    assert removed.diff[0].after is None
    assert removed.diff[0].evidence_removed == [E1, E2]


@pytest.mark.parametrize(
    ("evidence_id", "expected_error"),
    [
        ("evidence.missing", CandidateEvidenceNotFoundError),
        (CROSS_EVIDENCE, CandidateEvidenceProgramMismatchError),
    ],
)
def test_invalid_evidence_rolls_back_without_partial_candidate(
    candidate_database, evidence_id, expected_error
) -> None:
    _, _, sessions = candidate_database
    with sessions() as session:
        repository = CandidateRepository(
            session, clock=lambda: FIXED_NOW, id_factory=SequenceIds("invalid")
        )
        with pytest.raises(expected_error):
            repository.create(
                PROGRAM_ID,
                _candidate_payload(direct_evidence=evidence_id),
            )
        session.rollback()

    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(ProgramVersion)) == 0
        assert session.scalar(select(func.count()).select_from(ProgramFieldValue)) == 0
        assert session.scalar(select(func.count()).select_from(FieldEvidenceLink)) == 0
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_candidate_snapshot_content_cannot_be_updated_deleted_or_appended(
    candidate_database,
) -> None:
    _, _, sessions = candidate_database
    ids = SequenceIds("immutable")
    with sessions.begin() as session:
        candidate = CandidateRepository(
            session, clock=lambda: FIXED_NOW, id_factory=ids
        ).create(PROGRAM_ID, _candidate_payload())
    field_id = candidate.fields[0].id

    with sessions() as session:
        field = session.get(ProgramFieldValue, field_id)
        assert field is not None
        field.display_text = "Attempted mutation."
        with pytest.raises(CandidateImmutableError, match="不可修改"):
            session.commit()
        session.rollback()

    with sessions() as session:
        version = session.get(ProgramVersion, candidate.id)
        assert version is not None
        version.content_sha256 = "f" * 64
        with pytest.raises(CandidateImmutableError, match="不可修改"):
            session.commit()
        session.rollback()

    with sessions() as session:
        link = session.get(FieldEvidenceLink, (field_id, E1))
        assert link is not None
        link.support_scope = EvidenceSupportScope.APPLICABILITY
        with pytest.raises(CandidateImmutableError, match="不可修改"):
            session.commit()
        session.rollback()

    with sessions() as session:
        session.add(
            ProgramFieldValue(
                id="field.attempted.append",
                program_version_id=candidate.id,
                field_key="requirements.language.attempted",
                value_schema_version="program_requirement_field.v1",
                value_payload={},
                display_text="Attempted append.",
                is_critical=True,
                value_sha256="e" * 64,
            )
        )
        with pytest.raises(CandidateImmutableError, match="追加字段"):
            session.commit()
        session.rollback()

    with sessions() as session:
        field = session.get(ProgramFieldValue, field_id)
        assert field is not None
        session.delete(field)
        with pytest.raises(CandidateImmutableError, match="不可删除"):
            session.commit()
        session.rollback()

    with sessions() as session:
        unchanged = CandidateRepository(
            session, clock=lambda: FIXED_NOW, id_factory=ids
        ).get(candidate.id)
        assert unchanged == candidate


def test_candidate_record_survives_database_restart(candidate_database) -> None:
    url, first_engine, first_sessions = candidate_database
    ids = SequenceIds("restart")
    with first_sessions.begin() as session:
        created = CandidateRepository(
            session, clock=lambda: FIXED_NOW, id_factory=ids
        ).create(PROGRAM_ID, _candidate_payload())

    first_engine.dispose()
    second_engine = create_database_engine(url)
    second_sessions = create_session_factory(second_engine)
    with second_sessions() as session:
        restored = CandidateRepository(
            session, clock=lambda: FIXED_NOW, id_factory=ids
        ).get(created.id)

    assert restored == created
    assert restored is not None
    assert restored.created_at.tzinfo == timezone.utc
    second_engine.dispose()
