from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.app.db.migrations import upgrade_database
from backend.app.db.models import ProgramPublication
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.services.alpha_candidate_importer import AlphaCandidateImporter
from backend.app.services.internal_alpha_quality import (
    InternalAlphaQualityScanner,
    load_internal_alpha_quality_context,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALPHA_ROOT = PROJECT_ROOT / "backend" / "data" / "alpha_v1"
FRESH_NOW = datetime(2026, 9, 3, 15, 0, tzinfo=timezone.utc)


class PackIds:
    def __init__(self, version_id: str, namespace: str) -> None:
        self.version_id = version_id
        self.namespace = namespace
        self.counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        if kind == "version":
            return self.version_id
        count = self.counts.get(kind, 0) + 1
        self.counts[kind] = count
        return f"{kind}.internal.alpha.{self.namespace}.{count}"


@pytest.fixture
def internal_alpha_database(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'internal-alpha.sqlite3'}"
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    context = load_internal_alpha_quality_context(
        root=ALPHA_ROOT, generated_commit="internal-alpha-test"
    )
    for index, entry in enumerate(context.manifest.programs, start=1):
        with sessions.begin() as session:
            AlphaCandidateImporter(
                session,
                clock=lambda: FRESH_NOW,
                id_factory=PackIds(entry.candidate_version_id, str(index)),
            ).import_pack(
                pack=context.packs_by_ref[entry.pack_ref],
                scope=context.scope,
                idempotency_key=f"internal-alpha-test-{entry.pack_ref}",
            )
    yield sessions, context
    engine.dispose()


def _scan(sessions, context, now=FRESH_NOW):
    with sessions.begin() as session:
        return InternalAlphaQualityScanner(session, clock=lambda: now).scan(context)


def test_twenty_reviewed_candidates_pass_internal_alpha_quality_gate(
    internal_alpha_database,
):
    sessions, context = internal_alpha_database
    report = _scan(sessions, context)

    assert report.ready_for_internal_mvp is True
    assert report.program_count == 20
    assert report.blocking_gates == []
    assert all(item.passed for item in report.programs)
    assert all(
        metric.passed
        for metric in (
            report.gates.manifest_integrity,
            report.gates.pack_contract,
            report.gates.field_inventory,
            report.gates.official_fresh_evidence,
            report.gates.candidate_database_match,
            report.gates.candidate_only_isolation,
            report.gates.risk_and_exception_disclosure,
        )
    )
    assert sum(item.field_count for item in report.programs) == 302
    assert sum(item.evidence_count for item in report.programs) == 35
    assert any(item.high_risk_field_keys for item in report.programs)


def test_manifest_pack_hash_drift_fails_closed(internal_alpha_database):
    sessions, context = internal_alpha_database
    first = context.manifest.programs[0].model_copy(
        update={"pack_file_sha256": "f" * 64}
    )
    manifest = context.manifest.model_copy(
        update={"programs": [first, *context.manifest.programs[1:]]}
    )
    tampered = type(context)(
        root=context.root,
        scope=context.scope,
        manifest=manifest,
        packs_by_ref=context.packs_by_ref,
        pack_file_sha256_by_ref=context.pack_file_sha256_by_ref,
        generated_commit=context.generated_commit,
    )

    report = _scan(sessions, tampered)

    assert report.ready_for_internal_mvp is False
    assert "manifest_integrity" in report.blocking_gates
    assert "structural_contract" in report.blocking_gates


def test_due_evidence_blocks_internal_readiness(internal_alpha_database):
    sessions, context = internal_alpha_database

    report = _scan(
        sessions,
        context,
        now=datetime(2026, 10, 4, 0, 0, tzinfo=timezone.utc),
    )

    assert report.ready_for_internal_mvp is False
    assert "official_fresh_evidence" in report.blocking_gates


def test_any_publication_pointer_violates_candidate_only_boundary(
    internal_alpha_database,
):
    sessions, context = internal_alpha_database
    first = context.manifest.programs[0]
    with sessions.begin() as session:
        session.add(
            ProgramPublication(
                program_id=first.program_ref,
                current_version_id=first.candidate_version_id,
                revision=0,
                updated_at=FRESH_NOW,
            )
        )

    report = _scan(sessions, context)

    assert report.ready_for_internal_mvp is False
    assert "candidate_only_isolation" in report.blocking_gates
