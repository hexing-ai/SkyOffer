from __future__ import annotations

import json
import shutil
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import backend.tests.test_phase4_candidate_importer as importer_support
import backend.tests.test_phase4_manifest_contract as manifest_support
import backend.tests.test_phase4_program_pack_contract as pack_support
from backend.app.core.config import Settings
from backend.app.db.migrations import expected_head_revision, upgrade_database
from backend.app.db.models import (
    EvidenceAvailability,
    Program,
    ProgramPublication,
    ProgramVersion,
    SourceEvidence,
    SourceType,
)
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.main import create_app
from backend.app.repositories.candidates import CandidateRepository
from backend.app.schemas.alpha_manifest import (
    AlphaProgramManifestV1,
    AlphaScopeSnapshotV1,
)
from backend.app.schemas.alpha_program_pack import AlphaProgramPackV1
from backend.app.schemas.candidates import CandidateCreate
from backend.app.schemas.program_fields import ProgramDirection
from backend.app.schemas.version_workflow import (
    PublishVersionCommand,
    SubmitVersionCommand,
)
from backend.app.services.alpha_candidate_importer import AlphaCandidateImporter
from backend.app.services.alpha_manifest_validator import program_manifest_hash
from backend.app.services.alpha_quality_scanner import (
    AlphaQualityScanContext,
    AlphaQualityScanner,
    alpha_quality_report_is_current,
    load_alpha_quality_context,
)
from backend.app.services.version_workflow import VersionWorkflowService
from backend.scripts.audit_alpha_dataset import main as audit_main


FIXED_NOW = datetime(2026, 9, 2, 4, 0, tzinfo=timezone.utc)


class SequenceIds:
    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self.counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        count = self.counts.get(kind, 0) + 1
        self.counts[kind] = count
        return f"{kind}.{self.namespace}.{count}"


def _scope_institution(scope: AlphaScopeSnapshotV1, institution_ref: str):
    return next(
        item
        for item in (
            *scope.hong_kong_eight.institutions,
            *scope.united_kingdom_qs_top_100.institutions,
        )
        if item.institution_ref == institution_ref
    )


def _pack_for_entry(
    *, index: int, entry: dict, scope: AlphaScopeSnapshotV1
) -> AlphaProgramPackV1:
    is_low = entry["primary_direction"] == "low_altitude_economy"
    raw = pack_support._unsigned_pack_raw(low_altitude=is_low)
    institution = _scope_institution(scope, entry["institution_ref"])
    replacements = {
        "pack.synthetic.cs.01": entry["pack_ref"],
        "program.synthetic.cs.01": entry["program_ref"],
        "institution.synthetic.hk.01": entry["institution_ref"],
        "Synthetic Hong Kong Institution 01": institution.official_name,
        "Synthetic MSc Computer Science": f"Synthetic MSc Program {index:02d}",
        "evidence.synthetic.program": f"evidence.synthetic.{index:02d}.program",
        "evidence.synthetic.curriculum": (
            f"evidence.synthetic.{index:02d}.curriculum"
        ),
        "request.synthetic.pack.01": f"request.synthetic.pack.{index:02d}",
        "hk1.example.edu.hk": institution.registered_official_domain,
    }
    raw = importer_support._replace_strings(raw, replacements)
    raw["pack_ref"] = entry["pack_ref"]
    raw["scope_institution_ref"] = entry["institution_ref"]
    raw["program"]["program_ref"] = entry["program_ref"]
    raw["program"]["institution_name"] = institution.official_name
    raw["program"]["region"] = entry["region"]
    raw["program"]["registered_official_domain"] = (
        institution.registered_official_domain
    )
    raw["program"]["official_program_url"] = (
        f"https://www.{institution.registered_official_domain}/program-{index:02d}"
    )
    for evidence in raw["evidence"]:
        suffix = "curriculum" if evidence["reviewed_source_role"] == "curriculum" else "program"
        evidence["program_id"] = entry["program_ref"]
        evidence["url"] = (
            f"https://www.{institution.registered_official_domain}/"
            f"program-{index:02d}-{suffix}"
        )
        evidence["official_domain"] = f"www.{institution.registered_official_domain}"
    primary = next(
        field
        for field in raw["candidate"]["fields"]
        if field["field_key"] == "taxonomy.primary_direction"
    )
    primary["value_payload"]["value"]["direction"] = entry["primary_direction"]
    primary["display_text"] = entry["primary_direction"]
    raw["evidence"][0]["excerpt"] += f" {entry['primary_direction']}"
    return importer_support._resign(raw)


def _build_quality_root(root: Path) -> AlphaQualityScanContext:
    scope_raw, manifest_raw = manifest_support._build_frozen_fixture(root)
    scope = AlphaScopeSnapshotV1.model_validate(scope_raw)
    packs: dict[str, AlphaProgramPackV1] = {}
    file_hashes: dict[str, str] = {}
    for index, entry in enumerate(manifest_raw["programs"], start=1):
        pack = _pack_for_entry(index=index, entry=entry, scope=scope)
        path = root / entry["pack_path"]
        path.write_text(
            json.dumps(
                pack.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        file_hash = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
        entry["pack_sha256"] = file_hash
        packs[entry["pack_ref"]] = pack
        file_hashes[entry["pack_ref"]] = file_hash
    manifest = AlphaProgramManifestV1.model_validate(manifest_raw)
    manifest_raw["manifest_sha256"] = program_manifest_hash(manifest)
    (root / "manifest.json").write_text(
        json.dumps(manifest_raw, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (root / "scope_snapshot.json").write_text(
        json.dumps(scope_raw, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return load_alpha_quality_context(
        root=root,
        generated_commit="synthetic-quality-baseline",
        alembic_revision=expected_head_revision(),
    )


def _publish_imported(session, ids: SequenceIds, pack: AlphaProgramPackV1, scope):
    imported = AlphaCandidateImporter(
        session, clock=lambda: FIXED_NOW, id_factory=ids
    ).import_pack(
        pack=pack,
        scope=scope,
        idempotency_key=f"alpha-quality-import-key-{pack.pack_ref}",
    )
    workflow = VersionWorkflowService(
        session, clock=lambda: FIXED_NOW, id_factory=ids
    )
    workflow.submit(
        imported.candidate_version_id,
        SubmitVersionCommand(
            submitted_by="actor.data_preparer.codex",
            submission_note="Synthetic quality baseline submit.",
            request_id=f"request.submit.{pack.pack_ref}",
        ),
    )
    workflow.publish(
        imported.candidate_version_id,
        PublishVersionCommand(
            reviewed_by="actor.domain_reviewer.product_owner",
            review_note="Synthetic quality baseline publish.",
            request_id=f"request.publish.{pack.pack_ref}",
            expected_current_version_id=None,
        ),
    )


@pytest.fixture(scope="session")
def quality_template(tmp_path_factory):
    root = tmp_path_factory.mktemp("quality-root")
    context = _build_quality_root(root)
    database_path = tmp_path_factory.mktemp("quality-db") / "template.sqlite3"
    url = f"sqlite:///{database_path}"
    upgrade_database(url)
    engine = create_database_engine(url)
    sessions = create_session_factory(engine)
    ids = SequenceIds("quality-seed")
    for entry in context.manifest.programs:
        with sessions.begin() as session:
            _publish_imported(
                session, ids, context.packs_by_ref[entry.pack_ref], context.scope
            )
    engine.dispose()
    return root, database_path


@pytest.fixture
def quality_database(quality_template, tmp_path):
    root, template_database = quality_template
    database_path = tmp_path / "quality.sqlite3"
    shutil.copyfile(template_database, database_path)
    url = f"sqlite:///{database_path}"
    engine = create_database_engine(url)
    sessions = create_session_factory(engine)
    context = load_alpha_quality_context(
        root=root,
        generated_commit="synthetic-quality-baseline",
        alembic_revision=expected_head_revision(),
    )
    yield url, engine, sessions, context
    engine.dispose()


def _scan(sessions, context, *, now: datetime = FIXED_NOW):
    with sessions.begin() as session:
        return AlphaQualityScanner(session, clock=lambda: now).scan(context)


def _publish_mutated_candidate(
    session,
    *,
    context: AlphaQualityScanContext,
    pack_ref: str,
    ids: SequenceIds,
    mutate,
) -> str:
    pack = context.packs_by_ref[pack_ref]
    publication = session.get(ProgramPublication, pack.program.program_ref)
    assert publication is not None
    raw = pack.candidate.model_dump(mode="python")
    raw["base_version_id"] = publication.current_version_id
    raw["request_id"] = f"request.mutated.{ids.namespace}"
    mutate(raw)
    candidate = CandidateRepository(
        session, clock=lambda: FIXED_NOW, id_factory=ids
    ).create(pack.program.program_ref, CandidateCreate.model_validate(raw))
    workflow = VersionWorkflowService(
        session, clock=lambda: FIXED_NOW, id_factory=ids
    )
    workflow.submit(
        candidate.id,
        SubmitVersionCommand(
            submitted_by="actor.data_preparer.codex",
            submission_note="Synthetic negative quality submit.",
            request_id=f"request.submit.{ids.namespace}",
        ),
    )
    workflow.publish(
        candidate.id,
        PublishVersionCommand(
            reviewed_by="actor.domain_reviewer.product_owner",
            review_note="Synthetic negative quality publish.",
            request_id=f"request.publish.{ids.namespace}",
            expected_current_version_id=publication.current_version_id,
        ),
    )
    return candidate.id


def test_all_eight_quality_gates_pass_for_the_frozen_synthetic_dataset(
    quality_database,
) -> None:
    _, _, sessions, context = quality_database
    with sessions.begin() as session:
        counts_before = importer_support._counts(session)
    report = _scan(sessions, context)
    with sessions.begin() as session:
        assert importer_support._counts(session) == counts_before
    assert report.ready is True
    assert report.blocking_gates == []
    assert report.structural_issues == []
    assert report.published_program_count == 20
    for metric in report.hard_gates.model_dump(mode="python").values():
        assert metric["rate"] == 1
        assert metric["passed"] is True
    assert report.hard_gates.field_inventory_completion_rate.denominator == 305
    assert report.hard_gates.low_altitude_evidence_coverage_rate.denominator == 5
    assert report.generated_commit == "synthetic-quality-baseline"
    assert report.alembic_revision == expected_head_revision()


def test_api_returns_ready_false_and_specific_gate_after_freshness_failure(
    quality_database,
) -> None:
    _, _, sessions, context = quality_database
    first_entry = context.manifest.programs[0]
    with sessions.begin() as session:
        publication = session.get(ProgramPublication, first_entry.program_ref)
        assert publication is not None
        version = session.get(ProgramVersion, publication.current_version_id)
        assert version is not None
        version.published_at = datetime(2027, 4, 1, tzinfo=timezone.utc)

    app = create_app(
        Settings(_env_file=None, model_api_key=None),
        phase3_session_factory=sessions,
        phase3_clock=lambda: FIXED_NOW,
        phase3_id_factory=SequenceIds("quality-api"),
        phase4_quality_context_provider=lambda _dataset_id: context,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            f"/api/v1/internal/alpha-datasets/{context.manifest.dataset_id}/quality"
        )
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is False
    assert "fresh_evidence_at_publish_rate" in body["blocking_gates"]
    assert body["hard_gates"]["fresh_evidence_at_publish_rate"]["numerator"] == 19
    assert "excerpt" not in json.dumps(body)


def test_scope_and_four_eye_failures_are_traced_without_crashing_other_metrics(
    quality_database,
) -> None:
    _, _, sessions, context = quality_database
    first, second = context.manifest.programs[:2]
    with sessions.begin() as session:
        program = session.get(Program, first.program_ref)
        assert program is not None
        program.institution_name = "Synthetic out-of-scope identity"
        publication = session.get(ProgramPublication, second.program_ref)
        assert publication is not None
        version = session.get(ProgramVersion, publication.current_version_id)
        assert version is not None
        version.reviewed_by = version.submitted_by

    report = _scan(sessions, context)
    assert report.ready is False
    assert report.hard_gates.scope_compliance_rate.numerator == 19
    assert report.hard_gates.four_eye_review_rate.numerator == 19
    assert "scope_compliance_rate" in report.blocking_gates
    assert "four_eye_review_rate" in report.blocking_gates


def test_missing_field_reduces_fixed_registry_denominator_and_cannot_improve_rate(
    quality_database,
) -> None:
    _, _, sessions, context = quality_database
    pack_ref = context.manifest.programs[0].pack_ref
    before = _scan(sessions, context)

    def remove_department(raw: dict) -> None:
        raw["fields"] = [
            field
            for field in raw["fields"]
            if field["field_key"] != "catalog.department"
        ]

    with sessions.begin() as session:
        _publish_mutated_candidate(
            session,
            context=context,
            pack_ref=pack_ref,
            ids=SequenceIds("quality-missing-field"),
            mutate=remove_department,
        )
    after = _scan(sessions, context)
    assert before.hard_gates.field_inventory_completion_rate.denominator == 305
    assert after.hard_gates.field_inventory_completion_rate.denominator == 305
    assert after.hard_gates.field_inventory_completion_rate.numerator == 304
    assert after.ready is False
    assert "field_inventory_completion_rate" in after.blocking_gates


def test_unofficial_critical_citation_is_rejected(quality_database) -> None:
    _, _, sessions, context = quality_database
    pack_ref = context.manifest.programs[0].pack_ref
    pack = context.packs_by_ref[pack_ref]
    bad_evidence_id = "evidence.synthetic.unofficial.critical"
    with sessions.begin() as session:
        session.add(
            SourceEvidence(
                id=bad_evidence_id,
                program_id=pack.program.program_ref,
                source_type=SourceType.OFFICIAL_PROGRAM_PAGE,
                url="https://unofficial.example.org/program",
                official_domain="unofficial.example.org",
                page_title="Synthetic unofficial negative fixture",
                excerpt="computer_science",
                snapshot_sha256="f" * 64,
                source_version="synthetic negative fixture",
                captured_at=FIXED_NOW,
                verified_at=FIXED_NOW,
                verified_by="actor.data_preparer.codex",
                review_due_at=FIXED_NOW + timedelta(days=30),
                expires_at=FIXED_NOW + timedelta(days=60),
                availability_at_verification=EvidenceAvailability.AVAILABLE,
                capture_method="manual_browser",
                hash_scope="normalized_excerpt",
                reviewed_source_role="program",
                created_at=FIXED_NOW,
            )
        )

        def replace_primary_evidence(raw: dict) -> None:
            field = next(
                item
                for item in raw["fields"]
                if item["field_key"] == "taxonomy.primary_direction"
            )
            field["value_payload"]["reviewed_source_ids"] = [bad_evidence_id]
            field["evidence_links"] = [
                {
                    "evidence_id": bad_evidence_id,
                    "support_scope": "direct",
                    "citation_order": 1,
                }
            ]

        _publish_mutated_candidate(
            session,
            context=context,
            pack_ref=pack_ref,
            ids=SequenceIds("quality-unofficial-citation"),
            mutate=replace_primary_evidence,
        )
    report = _scan(sessions, context)
    assert report.hard_gates.critical_citation_coverage_rate.numerator == (
        report.hard_gates.critical_citation_coverage_rate.denominator - 1
    )
    assert "critical_citation_coverage_rate" in report.blocking_gates


def test_publication_pointer_to_candidate_fails_published_only_gate(
    quality_database,
) -> None:
    _, _, sessions, context = quality_database
    entry = context.manifest.programs[0]
    pack = context.packs_by_ref[entry.pack_ref]
    with sessions.begin() as session:
        publication = session.get(ProgramPublication, entry.program_ref)
        assert publication is not None
        raw = pack.candidate.model_dump(mode="python")
        raw["base_version_id"] = publication.current_version_id
        raw["request_id"] = "request.synthetic.pointer.candidate"
        candidate = CandidateRepository(
            session,
            clock=lambda: FIXED_NOW,
            id_factory=SequenceIds("quality-pointer"),
        ).create(entry.program_ref, CandidateCreate.model_validate(raw))
        publication.current_version_id = candidate.id
    report = _scan(sessions, context)
    assert report.hard_gates.published_only_isolation_rate.numerator == 19
    assert "published_only_isolation_rate" in report.blocking_gates


def test_low_altitude_and_pack_database_semantic_drift_fail_closed(
    quality_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, sessions, context = quality_database
    low_entry = next(
        entry
        for entry in context.manifest.programs
        if entry.primary_direction == ProgramDirection.LOW_ALTITUDE_ECONOMY
    )

    def remove_low_altitude_value(raw: dict) -> None:
        field = next(
            item
            for item in raw["fields"]
            if item["field_key"] == "taxonomy.low_altitude_basis"
        )
        detail = "Low-altitude basis requires renewed manual review."
        field["value_payload"]["coverage_status"] = "manual_review"
        field["value_payload"]["value"] = None
        field["value_payload"]["reason"] = {
            "reason_code": "OFFICIAL_RULE_AMBIGUOUS",
            "detail": detail,
        }
        field["value_payload"]["review_note"] = detail
        field["display_text"] = detail

    # Seed a legacy/corrupted published state by bypassing only the new workflow
    # validator; the quality scanner must independently detect the same defect.
    monkeypatch.setattr(
        "backend.app.services.version_workflow.validate_low_altitude_taxonomy",
        lambda **_kwargs: None,
    )
    with sessions.begin() as session:
        _publish_mutated_candidate(
            session,
            context=context,
            pack_ref=low_entry.pack_ref,
            ids=SequenceIds("quality-low-altitude"),
            mutate=remove_low_altitude_value,
        )
    report = _scan(sessions, context)
    assert report.hard_gates.low_altitude_evidence_coverage_rate.numerator == 4
    assert "low_altitude_evidence_coverage_rate" in report.blocking_gates
    assert report.hard_gates.pack_to_database_semantic_match_rate.numerator == 19
    assert "pack_to_database_semantic_match_rate" in report.blocking_gates


def test_old_report_becomes_stale_when_pack_or_manifest_identity_changes(
    quality_database,
) -> None:
    _, _, sessions, context = quality_database
    report = _scan(sessions, context)
    assert alpha_quality_report_is_current(report, context)
    first_ref = context.manifest.programs[0].pack_ref
    changed_packs = dict(context.packs_by_ref)
    changed_packs[first_ref] = changed_packs[first_ref].model_copy(
        update={"pack_canonical_sha256": "f" * 64}
    )
    changed_context = replace(context, packs_by_ref=changed_packs)
    assert not alpha_quality_report_is_current(report, changed_context)

    changed_fact = dict(context.packs_by_ref)
    changed_program = changed_fact[first_ref].program.model_copy(
        update={"official_name": "Mutated in-memory Program fact"}
    )
    changed_fact[first_ref] = changed_fact[first_ref].model_copy(
        update={"program": changed_program}
    )
    assert not alpha_quality_report_is_current(
        report, replace(context, packs_by_ref=changed_fact)
    )


def test_cli_returns_nonzero_for_current_empty_unpublished_skeleton(
    tmp_path, capsys
) -> None:
    url = f"sqlite:///{tmp_path / 'empty-quality.sqlite3'}"
    upgrade_database(url)
    exit_code = audit_main(
        [
            "--root",
            str(manifest_support.DATA_ROOT),
            "--generated-commit",
            "synthetic-empty-scan",
            "--database-url",
            url,
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert output["ready"] is False
