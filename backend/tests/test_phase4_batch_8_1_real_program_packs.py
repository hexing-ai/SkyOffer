from __future__ import annotations

import hashlib
import json
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
    "hku_msc_computer_science_2027_v1.json": {
        "file_hash": "781e0590367b98bc219bad9bd7a5401e11dbc7a6a60d03e615b47ebb5a87ddc5",
        "pack_hash": "df53b6fadd8deb2cbe72e4dae91a8e83e1cb2b1c26fae3c8890703532f9c0d5f",
        "semantic_hash": "0c4cd8b351720f48525563b96729a27e55cee796222ef86102943f67d044a5ea",
        "evidence_count": 1,
    },
    "hkust_msc_aeronautical_engineering_2027_v1.json": {
        "file_hash": "0af8d6c39427be4ee0262362805b4b2b5b1ef64d16bb1dfc5750c2478861c945",
        "pack_hash": "b9304e8e0d43fd56037f5cf75ddfac6f65f3be1ba0ad99599dc7c85795d33501",
        "semantic_hash": "1bd5f5a668ad4b14dc7fa72b5a40f782deb3a093622e0e442f32c2478cadaf6b",
        "evidence_count": 2,
    },
}


class StableIds:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        count = self.counts.get(kind, 0) + 1
        self.counts[kind] = count
        return f"{kind}.phase4.batch8.1.{count}"


def _load_pack(path: Path) -> AlphaProgramPackV1:
    return AlphaProgramPackV1.model_validate_json(path.read_text(encoding="utf-8"))


def test_batch_8_1_real_pack_files_are_frozen_and_validate_offline() -> None:
    actual_files = {path.name for path in PROGRAM_DIR.glob("*.json")}
    assert set(PACKS).issubset(actual_files)
    assert "bristol_msc_aerial_robotics_2027_v1.json" not in actual_files

    for filename, expected in PACKS.items():
        pack_bytes = (PROGRAM_DIR / filename).read_bytes()
        assert hashlib.sha256(pack_bytes).hexdigest() == expected["file_hash"]
        report = validate_alpha_program_pack_files(
            pack_path=PROGRAM_DIR / filename,
            scope_path=SCOPE_PATH,
        )
        assert report.valid is True
        assert report.scope_snapshot_id == "scope.alpha.2027.v2"
        assert report.field_count == 15
        assert report.evidence_count == expected["evidence_count"]
        assert report.computed_pack_canonical_sha256 == expected["pack_hash"]
        assert report.computed_semantic_content_sha256 == expected["semantic_hash"]

        pack = _load_pack(PROGRAM_DIR / filename)
        assert pack.pack_canonical_sha256 == expected["pack_hash"]
        assert pack.expected_semantic_content_sha256 == expected["semantic_hash"]
        assert all(item.capture_method == "manual_browser" for item in pack.evidence)
        assert all(item.hash_scope == "normalized_excerpt" for item in pack.evidence)
        assert all(
            item.snapshot_sha256
            == hashlib.sha256(item.excerpt.encode("utf-8")).hexdigest()
            for item in pack.evidence
        )


def test_batch_8_1_keeps_manifest_empty_and_non_publishable() -> None:
    manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["template_state"] == "empty_unreviewed"
    assert manifest["publishable"] is False
    assert manifest["programs"] == []
    assert manifest["manifest_sha256"] is None


def test_batch_8_1_imports_two_candidates_and_never_publishes(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'phase4-batch8-1.sqlite3'}"
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    scope = AlphaScopeSnapshotV1.model_validate_json(
        SCOPE_PATH.read_text(encoding="utf-8")
    )
    packs = [_load_pack(PROGRAM_DIR / filename) for filename in sorted(PACKS)]
    report = AlphaCandidateBatchImporter(
        sessions,
        clock=lambda: datetime(2026, 9, 3, 8, 0, tzinfo=timezone.utc),
        id_factory=StableIds(),
    ).import_commands(
        AlphaCandidateImportCommand(
            pack=pack,
            scope=scope,
            idempotency_key=f"phase4-batch8-1-{pack.pack_ref}",
        )
        for pack in packs
    )

    assert report.complete is True
    assert report.attempted_count == 2
    assert report.imported_count == 2
    assert report.failed_count == 0
    assert all(item.result is not None for item in report.items)

    with sessions.begin() as session:
        assert session.scalar(select(func.count()).select_from(Program)) == 2
        assert session.scalar(select(func.count()).select_from(SourceEvidence)) == 3
        assert session.scalar(select(func.count()).select_from(ProgramVersion)) == 2
        assert session.scalar(select(func.count()).select_from(ProgramFieldValue)) == 30
        assert session.scalar(select(func.count()).select_from(ProgramPublication)) == 0
        versions = session.scalars(select(ProgramVersion)).all()
        assert {version.status for version in versions} == {VersionStatus.CANDIDATE}
        assert {version.content_sha256 for version in versions} == {
            pack.expected_semantic_content_sha256 for pack in packs
        }

    engine.dispose()
