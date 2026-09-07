from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from backend.app.db.migrations import upgrade_database
from backend.app.db.models import (
    EvidenceAvailability,
    EvidenceSupportScope,
    FieldEvidenceLink,
    Program,
    ProgramFieldValue,
    ProgramRegion,
    ProgramVersion,
    SourceEvidence,
    VersionStatus,
)
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.repositories.evidence import (
    EvidenceAlreadyExistsError,
    EvidenceImmutableError,
    EvidenceOfficialDomainMismatchError,
    EvidenceProgramNotFoundError,
    SourceEvidenceRepository,
)
from backend.app.schemas.evidence import (
    EvidenceFreshness,
    SourceEvidenceCreate,
    derive_evidence_freshness,
)


PROGRAM_ID = "program.pilot.edinburgh.computer_science_msc"
EVIDENCE_ID = "evidence.pilot.edinburgh.cs.ielts.2026_27"
FIXED_NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def evidence_payload() -> dict:
    return {
        "id": EVIDENCE_ID,
        "program_id": PROGRAM_ID,
        "source_type": "official_program_page",
        "url": (
            "https://Study.Ed.Ac.Uk/programmes/postgraduate-taught/110-computer-science"
            "?view=entry&lang=en#entry-requirements"
        ),
        "official_domain": "Study.Ed.Ac.Uk.",
        "page_title": (
            "Computer Science MSc - Postgraduate taught programmes | "
            "The University of Edinburgh"
        ),
        "excerpt": (
            "IELTS Academic: total 7.0 with at least 6.5 in each component We do not "
            "accept IELTS One Skill Retake to meet our English language requirements."
        ),
        "snapshot_sha256": (
            "b991bedc92cae1b638867cad5ff3efa88db7e33016db9b899cb86df737a40a01"
        ),
        "source_version": "degree-finder-entry-2026; academic year 2026-27",
        "captured_at": "2026-09-01T08:00:00+08:00",
        "verified_at": "2026-09-01T08:00:00+08:00",
        "verified_by": "actor.domain_reviewer.product_owner",
        "review_due_at": "2026-10-01T00:00:00Z",
        "expires_at": "2026-10-08T00:00:00Z",
        "availability_at_verification": "available",
    }


@pytest.fixture
def evidence_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'evidence.sqlite3'}"
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
                official_program_url=(
                    "https://study.ed.ac.uk/programmes/postgraduate-taught/110-computer-science"
                ),
                registered_official_domain="ed.ac.uk",
                created_at=FIXED_NOW,
            )
        )
    yield url, engine, sessions
    engine.dispose()


def test_schema_normalizes_official_url_domain_and_utc_timestamps() -> None:
    payload = evidence_payload()
    payload["url"] = (
        "https://Study.Ed.Ac.Uk/programmes/example?z=2&a=1&a=0#requirements"
    )
    validated = SourceEvidenceCreate.model_validate(payload)

    assert validated.url == (
        "https://study.ed.ac.uk/programmes/example?a=0&a=1&z=2"
    )
    assert validated.official_domain == "study.ed.ac.uk"
    assert validated.captured_at == datetime(2026, 9, 1, tzinfo=timezone.utc)
    assert validated.url.endswith("a=0&a=1&z=2")
    assert "#" not in validated.url


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("url", "http://study.ed.ac.uk/programmes/example"),
        ("url", "https://user:secret@study.ed.ac.uk/programmes/example"),
        ("url", "https://study.ed.ac.uk:8443/programmes/example"),
        ("official_domain", "localhost"),
        ("excerpt", ""),
        ("snapshot_sha256", "A" * 64),
        ("snapshot_sha256", "a" * 63),
        ("captured_at", "2026-09-01T00:00:00"),
    ],
)
def test_schema_rejects_invalid_evidence_fields(field: str, invalid_value) -> None:
    payload = evidence_payload()
    payload[field] = invalid_value

    with pytest.raises(ValidationError):
        SourceEvidenceCreate.model_validate(payload)


def test_schema_rejects_unknown_fields_and_invalid_time_order() -> None:
    payload = evidence_payload()
    payload["freshness"] = "fresh"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SourceEvidenceCreate.model_validate(payload)

    payload = evidence_payload()
    payload["expires_at"] = payload["review_due_at"]
    with pytest.raises(ValidationError, match="expires_at must be after review_due_at"):
        SourceEvidenceCreate.model_validate(payload)


def test_repository_creates_and_reads_immutable_evidence_after_restart(
    evidence_database,
) -> None:
    url, first_engine, first_sessions = evidence_database
    payload = SourceEvidenceCreate.model_validate(evidence_payload())

    with first_sessions.begin() as session:
        repository = SourceEvidenceRepository(session, clock=lambda: FIXED_NOW)
        created = repository.create(payload)
        assert created.freshness == EvidenceFreshness.FRESH
        assert created.url == (
            "https://study.ed.ac.uk/programmes/postgraduate-taught/110-computer-science"
            "?lang=en&view=entry"
        )
        assert not hasattr(repository, "update")
        assert not hasattr(repository, "delete")

    first_engine.dispose()

    second_engine = create_database_engine(url)
    second_sessions = create_session_factory(second_engine)
    with second_sessions() as session:
        repository = SourceEvidenceRepository(session, clock=lambda: FIXED_NOW)
        restored = repository.get(EVIDENCE_ID)
        assert restored is not None
        assert restored == created
        assert restored.created_at.tzinfo == timezone.utc
        assert [record.id for record in repository.list_for_program(PROGRAM_ID)] == [
            EVIDENCE_ID
        ]
    second_engine.dispose()


def test_repository_accepts_evidence_from_program_official_domain_alias(
    evidence_database,
) -> None:
    _, _, sessions = evidence_database
    alias_payload = evidence_payload()
    alias_payload["id"] = "evidence.pilot.edinburgh.cs.alias.2026_27"
    alias_payload["url"] = "https://catalog.edinburgh-example.ac.uk/program"
    alias_payload["official_domain"] = "catalog.edinburgh-example.ac.uk"

    with sessions.begin() as session:
        program = session.get(Program, PROGRAM_ID)
        assert program is not None
        program.official_domain_aliases = ["edinburgh-example.ac.uk"]

    with sessions.begin() as session:
        repository = SourceEvidenceRepository(session, clock=lambda: FIXED_NOW)
        created = repository.create(SourceEvidenceCreate.model_validate(alias_payload))
        assert created.official_domain == "catalog.edinburgh-example.ac.uk"


def test_repository_rejects_wrong_domain_missing_program_and_duplicate(
    evidence_database,
) -> None:
    _, _, sessions = evidence_database

    with sessions() as session:
        wrong_domain = evidence_payload()
        wrong_domain["url"] = "https://admissions.example.com/programmes/example"
        wrong_domain["official_domain"] = "admissions.example.com"
        repository = SourceEvidenceRepository(session, clock=lambda: FIXED_NOW)
        with pytest.raises(EvidenceOfficialDomainMismatchError):
            repository.create(SourceEvidenceCreate.model_validate(wrong_domain))

    with sessions() as session:
        missing_program = evidence_payload()
        missing_program["program_id"] = "program.missing"
        repository = SourceEvidenceRepository(session, clock=lambda: FIXED_NOW)
        with pytest.raises(EvidenceProgramNotFoundError):
            repository.create(SourceEvidenceCreate.model_validate(missing_program))

    with sessions.begin() as session:
        repository = SourceEvidenceRepository(session, clock=lambda: FIXED_NOW)
        payload = SourceEvidenceCreate.model_validate(evidence_payload())
        repository.create(payload)
        with pytest.raises(EvidenceAlreadyExistsError):
            repository.create(payload)


def test_persisted_evidence_cannot_be_updated_or_deleted(evidence_database) -> None:
    _, _, sessions = evidence_database
    payload = SourceEvidenceCreate.model_validate(evidence_payload())

    with sessions.begin() as session:
        SourceEvidenceRepository(session, clock=lambda: FIXED_NOW).create(payload)

    with sessions() as session:
        evidence = session.get(SourceEvidence, EVIDENCE_ID)
        assert evidence is not None
        evidence.excerpt = "attempted overwrite"
        with pytest.raises(EvidenceImmutableError, match="不可修改"):
            session.commit()
        session.rollback()

        evidence = session.get(SourceEvidence, EVIDENCE_ID)
        assert evidence is not None
        session.delete(evidence)
        with pytest.raises(EvidenceImmutableError, match="不可删除"):
            session.commit()
        session.rollback()

    with sessions() as session:
        unchanged = session.get(SourceEvidence, EVIDENCE_ID)
        assert unchanged is not None
        assert unchanged.excerpt == payload.excerpt


def test_immutability_guard_allows_new_links_without_mutating_evidence(
    evidence_database,
) -> None:
    _, _, sessions = evidence_database
    payload = SourceEvidenceCreate.model_validate(evidence_payload())

    with sessions.begin() as session:
        SourceEvidenceRepository(session, clock=lambda: FIXED_NOW).create(payload)

    with sessions.begin() as session:
        session.add(
            ProgramVersion(
                id="version.pilot.link-test",
                program_id=PROGRAM_ID,
                version_no=1,
                status=VersionStatus.CANDIDATE,
                content_schema_version="program_version_content.v1",
                content_sha256="a" * 64,
                created_by="actor.data_preparer.codex",
                created_at=FIXED_NOW,
            )
        )
        session.add(
            ProgramFieldValue(
                id="field.pilot.link-test",
                program_version_id="version.pilot.link-test",
                field_key="requirements.language.ielts",
                value_schema_version="program_requirement_field.v1",
                value_payload={"test": "relationship-only-change"},
                display_text="Relationship-only immutability test.",
                is_critical=True,
                value_sha256="b" * 64,
            )
        )
        evidence = session.get(SourceEvidence, EVIDENCE_ID)
        assert evidence is not None
        evidence.field_links.append(
            FieldEvidenceLink(
                field_value_id="field.pilot.link-test",
                evidence_id=EVIDENCE_ID,
                support_scope=EvidenceSupportScope.DIRECT,
                citation_order=1,
            )
        )

    with sessions() as session:
        evidence = session.get(SourceEvidence, EVIDENCE_ID)
        assert evidence is not None
        assert evidence.excerpt == payload.excerpt
        assert len(evidence.field_links) == 1


def test_freshness_is_derived_from_injected_clock() -> None:
    review_due = FIXED_NOW + timedelta(days=1)
    expires = FIXED_NOW + timedelta(days=2)

    assert derive_evidence_freshness(
        availability=EvidenceAvailability.AVAILABLE,
        review_due_at=review_due,
        expires_at=expires,
        now=FIXED_NOW,
    ) == EvidenceFreshness.FRESH
    assert derive_evidence_freshness(
        availability=EvidenceAvailability.AVAILABLE,
        review_due_at=review_due,
        expires_at=expires,
        now=review_due,
    ) == EvidenceFreshness.REVIEW_DUE
    assert derive_evidence_freshness(
        availability=EvidenceAvailability.AVAILABLE,
        review_due_at=review_due,
        expires_at=expires,
        now=expires,
    ) == EvidenceFreshness.EXPIRED
    assert derive_evidence_freshness(
        availability=EvidenceAvailability.SOURCE_UNAVAILABLE,
        review_due_at=review_due,
        expires_at=expires,
        now=FIXED_NOW,
    ) == EvidenceFreshness.SOURCE_UNAVAILABLE
