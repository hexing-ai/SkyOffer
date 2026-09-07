from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from backend.app.db.migrations import upgrade_database
from backend.app.db.models import (
    Program,
    ProgramFieldValue,
    ProgramPublication,
    ProgramVersion,
    SourceEvidence,
    VersionStatus,
)
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.schemas.alpha_manifest import AlphaScopeSnapshotV1
from backend.app.schemas.alpha_program_pack import AlphaProgramPackV1
from backend.app.schemas.program_fields import ProgramRequirementFieldV2
from backend.app.services.alpha_candidate_importer import (
    AlphaCandidateBatchImporter,
    AlphaCandidateImportCommand,
)
from backend.app.services.alpha_program_pack_validator import (
    validate_alpha_program_pack_files,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "backend" / "data" / "alpha_v1"
PROGRAM_DIR = DATA_DIR / "programs"
SCOPE_PATH = DATA_DIR / "scope_snapshot.json"
PACKS = {
    "hkust_msc_information_technology_2027_v1.json": {
        "file_hash": "18129395e8e3880aee7cb3941a039379f176b0267e1844b239ec8aefebbf382d",
        "pack_hash": "dd1ebc818edb17d0c8ebdc5d37e2638f3999b3c67b48c5277831aec2ebe70dd2",
        "semantic_hash": "1988f74e11c52aaa735a514629abf600ecc647323714a88df25a6497598ea2df",
    },
    "hkust_msc_artificial_intelligence_2027_v1.json": {
        "file_hash": "c3d67dfa5c99ddbbdbdad5d97e89c7424aa82c6d31120492a6a10c89dd567499",
        "pack_hash": "14ac0eb791b6c85b8b541133f73bcf10715d2f0178d8426b3c383322e0c85dec",
        "semantic_hash": "575565436b29fc11e72dff83a083f9aa71b9a51e9b594dc634833873de7c5035",
    },
}


class StableIds:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        count = self.counts.get(kind, 0) + 1
        self.counts[kind] = count
        return f"{kind}.phase4.batch8.2.{count}"


def _load_pack(filename: str) -> AlphaProgramPackV1:
    return AlphaProgramPackV1.model_validate_json(
        (PROGRAM_DIR / filename).read_text(encoding="utf-8")
    )


def _field(pack: AlphaProgramPackV1, field_key: str):
    return next(item for item in pack.candidate.fields if item.field_key == field_key)


def test_batch_8_2_real_pack_files_are_frozen_and_validate_offline() -> None:
    actual_files = {path.name for path in PROGRAM_DIR.glob("*.json")}
    assert set(PACKS).issubset(actual_files)
    assert "hku_msc_artificial_intelligence_2027_v1.json" not in actual_files

    for filename, expected in PACKS.items():
        path = PROGRAM_DIR / filename
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected["file_hash"]
        report = validate_alpha_program_pack_files(
            pack_path=path,
            scope_path=SCOPE_PATH,
        )
        assert report.valid is True
        assert report.scope_snapshot_id == "scope.alpha.2027.v2"
        assert report.field_count == 15
        assert report.evidence_count == 3
        assert report.computed_pack_canonical_sha256 == expected["pack_hash"]
        assert report.computed_semantic_content_sha256 == expected["semantic_hash"]

        pack = _load_pack(filename)
        assert pack.pack_canonical_sha256 == expected["pack_hash"]
        assert pack.expected_semantic_content_sha256 == expected["semantic_hash"]
        assert all(item.capture_method == "manual_browser" for item in pack.evidence)
        assert all(
            item.snapshot_sha256
            == hashlib.sha256(item.excerpt.encode("utf-8")).hexdigest()
            for item in pack.evidence
        )


def test_batch_8_2_duplicates_shared_policy_per_program_and_keeps_rules_isolated() -> None:
    it_pack = _load_pack("hkust_msc_information_technology_2027_v1.json")
    ai_pack = _load_pack("hkust_msc_artificial_intelligence_2027_v1.json")
    assert set(it_pack.reviewed_source_ids).isdisjoint(ai_pack.reviewed_source_ids)

    it_policy = next(
        item for item in it_pack.evidence if item.url.endswith("admission-requirements")
    )
    ai_policy = next(
        item for item in ai_pack.evidence if item.url.endswith("admission-requirements")
    )
    assert it_policy.reviewed_source_role == "language_policy"
    assert ai_policy.reviewed_source_role == "language_policy"
    assert it_policy.id != ai_policy.id
    assert it_policy.program_id == it_pack.program.program_ref
    assert ai_policy.program_id == ai_pack.program.program_ref
    assert it_policy.url == ai_policy.url
    assert it_policy.snapshot_sha256 == ai_policy.snapshot_sha256

    it_work = _field(it_pack, "requirements.work_experience").value_payload
    ai_work = _field(ai_pack, "requirements.work_experience").value_payload
    assert isinstance(it_work, ProgramRequirementFieldV2)
    assert isinstance(ai_work, ProgramRequirementFieldV2)
    assert it_work.coverage_status == "not_found_in_reviewed_sources"
    assert it_work.requirements == []
    assert ai_work.coverage_status == "confirmed"
    assert len(ai_work.requirements) == 1
    ai_requirement = ai_work.requirements[0]
    assert ai_requirement.applicability is not None
    assert ai_requirement.applicability.operator == "manual_review"
    assert ai_requirement.rule.operator == "duration_min_months"
    assert ai_requirement.rule.minimum_months == 24

    it_subject = _field(it_pack, "requirements.subject").display_text
    ai_subject = _field(ai_pack, "requirements.subject").display_text
    assert it_subject != ai_subject
    assert "recognized university or tertiary institution" in it_subject
    assert "other disciplines" not in it_subject
    assert "related discipline" in ai_subject


def test_batch_8_2_imports_two_isolated_candidates_and_never_publishes(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'phase4-batch8-2.sqlite3'}"
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    scope = AlphaScopeSnapshotV1.model_validate_json(
        SCOPE_PATH.read_text(encoding="utf-8")
    )
    packs = [_load_pack(filename) for filename in sorted(PACKS)]
    importer = AlphaCandidateBatchImporter(
        sessions,
        clock=lambda: datetime(2026, 9, 3, 8, 30, tzinfo=timezone.utc),
        id_factory=StableIds(),
    )
    commands = [
        AlphaCandidateImportCommand(
            pack=pack,
            scope=scope,
            idempotency_key=f"phase4-batch8-2-{pack.pack_ref}",
        )
        for pack in packs
    ]
    first = importer.import_commands(commands)
    replay = importer.import_commands(commands)
    assert first.complete is True
    assert replay == first

    with sessions.begin() as session:
        assert session.scalar(select(func.count()).select_from(Program)) == 2
        assert session.scalar(select(func.count()).select_from(SourceEvidence)) == 6
        assert session.scalar(select(func.count()).select_from(ProgramVersion)) == 2
        assert session.scalar(select(func.count()).select_from(ProgramFieldValue)) == 30
        assert session.scalar(select(func.count()).select_from(ProgramPublication)) == 0
        versions = session.scalars(select(ProgramVersion)).all()
        assert {version.status for version in versions} == {VersionStatus.CANDIDATE}
        assert {version.content_sha256 for version in versions} == {
            pack.expected_semantic_content_sha256 for pack in packs
        }

    engine.dispose()
