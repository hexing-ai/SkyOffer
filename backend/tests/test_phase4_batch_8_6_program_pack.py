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
MATRIX_PATH = DATA_DIR / "sources" / "alpha_program_candidate_matrix_2027_v1.json"
PACK_FILENAME = "manchester_msc_advanced_computer_science_2027_v1.json"
PACK_PATH = PROGRAM_DIR / PACK_FILENAME
PROGRAM_REF = "program.uk.manchester.msc_advanced_computer_science"
EXPECTED_FILE_HASH = "b39c99188b2d02cb8ff0c8cbf3122a85995a9901908f5104de7b221fe91f9496"
EXPECTED_PACK_HASH = "8db15baba5fb48745bfcc7f8584e18a4eda53808cd205c4111c96d5e5d4631db"
EXPECTED_SEMANTIC_HASH = (
    "e8050e504adb41d3f4181f67c587793735051c25f7b318ef045b9827dccc23b5"
)
MATRIX_PROGRAMS = (
    {
        "program_ref": "program.uk.edinburgh.msc_computer_science",
        "pack_filename": "edinburgh_msc_computer_science_2027_v1.json",
        "primary_direction": "computer_science",
        "secondary_directions": [],
        "target_year_status": "current_official_page_2027_not_explicit",
    },
    {
        "program_ref": "program.uk.edinburgh.msc_artificial_intelligence",
        "pack_filename": "edinburgh_msc_artificial_intelligence_2027_v1.json",
        "primary_direction": "artificial_intelligence",
        "secondary_directions": ["computer_science"],
        "target_year_status": "current_official_page_2027_not_explicit",
    },
    {
        "program_ref": PROGRAM_REF,
        "pack_filename": PACK_FILENAME,
        "primary_direction": "computer_science",
        "secondary_directions": [],
        "target_year_status": "2027_entry_explicit",
    },
)


class StableIds:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        count = self.counts.get(kind, 0) + 1
        self.counts[kind] = count
        return f"{kind}.phase4.batch8.6.test.{count}"


def _load_pack() -> AlphaProgramPackV1:
    return AlphaProgramPackV1.model_validate_json(PACK_PATH.read_text(encoding="utf-8"))


def _field(pack: AlphaProgramPackV1, field_key: str):
    return next(item for item in pack.candidate.fields if item.field_key == field_key)


def test_batch_8_6_splits_blocked_ed_inburgh_from_valid_manchester_pack() -> None:
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    actual_files = {path.name for path in PROGRAM_DIR.glob("*.json")}
    entries = {item["program_ref"]: item for item in matrix["programs"]}

    matrix_order = [item["program_ref"] for item in matrix["programs"]]
    expected_order = [item["program_ref"] for item in MATRIX_PROGRAMS]
    start = matrix_order.index(expected_order[0])
    assert matrix_order[start : start + len(expected_order)] == expected_order

    for expected in MATRIX_PROGRAMS:
        entry = entries[expected["program_ref"]]
        assert entry["primary_direction"] == expected["primary_direction"]
        assert entry["secondary_directions"] == expected["secondary_directions"]
        assert entry["target_year_status"] == expected["target_year_status"]

    assert MATRIX_PROGRAMS[0]["pack_filename"] not in actual_files
    assert MATRIX_PROGRAMS[1]["pack_filename"] not in actual_files
    assert PACK_FILENAME in actual_files

    assert hashlib.sha256(PACK_PATH.read_bytes()).hexdigest() == EXPECTED_FILE_HASH
    report = validate_alpha_program_pack_files(
        pack_path=PACK_PATH,
        scope_path=SCOPE_PATH,
    )
    assert report.valid is True
    assert report.field_count == 15
    assert report.evidence_count == 4
    assert report.computed_pack_canonical_sha256 == EXPECTED_PACK_HASH
    assert report.computed_semantic_content_sha256 == EXPECTED_SEMANTIC_HASH


def test_batch_8_6_preserves_field_level_rules_and_fee_boundary() -> None:
    pack = _load_pack()
    assert pack.pack_canonical_sha256 == EXPECTED_PACK_HASH
    assert pack.expected_semantic_content_sha256 == EXPECTED_SEMANTIC_HASH
    assert all(item.capture_method == "manual_browser" for item in pack.evidence)
    assert all(
        item.snapshot_sha256
        == hashlib.sha256(item.excerpt.encode("utf-8")).hexdigest()
        for item in pack.evidence
    )
    assert {item.reviewed_source_role for item in pack.evidence} == {
        "program",
        "admissions_policy",
        "language_policy",
        "curriculum",
    }
    assert all("fee" not in item.field_key for item in pack.candidate.fields)

    intake = _field(pack, "catalog.intake").value_payload
    assert intake.coverage_status == "not_found_in_reviewed_sources"
    assert intake.value is None

    application = _field(pack, "catalog.application_status").value_payload
    assert application.coverage_status == "confirmed"
    assert application.value.status == "open"
    assert application.value.closes_on.isoformat() == "2027-05-21"

    academic = _field(pack, "requirements.academic").value_payload
    assert isinstance(academic, ProgramRequirementFieldV2)
    academic_rule = academic.requirements[0].rule
    assert academic_rule.operator == "case"
    assert academic_rule.cases["china_mainland"].operator == "numeric_min"
    assert academic_rule.cases["china_mainland"].minimum == 87
    assert academic_rule.cases["china_mainland"].scale == 100

    subject = _field(pack, "requirements.subject").value_payload
    assert isinstance(subject, ProgramRequirementFieldV2)
    subject_rule = subject.requirements[0].rule
    assert subject_rule.operator == "all"
    assert subject_rule.children[0].operator == "set_intersects"
    assert subject_rule.children[0].accepted_values == {"computer_science"}
    assert subject_rule.children[1].operator == "manual_review"

    language = _field(pack, "requirements.language").value_payload
    assert isinstance(language, ProgramRequirementFieldV2)
    language_rule = language.requirements[0].rule
    assert language_rule.operator == "any"
    assert len(language_rule.children) == 3

    work = _field(pack, "requirements.work_experience").value_payload
    materials = _field(pack, "requirements.materials").value_payload
    assert work.coverage_status == "manual_review"
    assert materials.coverage_status == "manual_review"
    assert work.requirements == []
    assert materials.requirements == []


def test_batch_8_6_imports_one_candidate_idempotently_and_never_publishes(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'phase4-batch8-6.sqlite3'}"
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    scope = AlphaScopeSnapshotV1.model_validate_json(
        SCOPE_PATH.read_text(encoding="utf-8")
    )
    pack = _load_pack()
    importer = AlphaCandidateBatchImporter(
        sessions,
        clock=lambda: datetime(2026, 9, 3, 12, 30, tzinfo=timezone.utc),
        id_factory=StableIds(),
    )
    commands = [
        AlphaCandidateImportCommand(
            pack=pack,
            scope=scope,
            idempotency_key=f"phase4-batch8-6-{pack.pack_ref}",
        )
    ]
    first = importer.import_commands(commands)
    replay = importer.import_commands(commands)
    assert first.complete is True
    assert replay == first

    with sessions.begin() as session:
        assert session.scalar(select(func.count()).select_from(Program)) == 1
        assert session.scalar(select(func.count()).select_from(SourceEvidence)) == 4
        assert session.scalar(select(func.count()).select_from(ProgramVersion)) == 1
        assert session.scalar(select(func.count()).select_from(ProgramFieldValue)) == 15
        assert session.scalar(select(func.count()).select_from(ProgramPublication)) == 0
        version = session.scalar(select(ProgramVersion))
        assert version is not None
        assert version.status == VersionStatus.CANDIDATE
        assert version.content_sha256 == EXPECTED_SEMANTIC_HASH

    engine.dispose()
