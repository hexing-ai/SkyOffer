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
PACK_FILENAME = "manchester_msc_aerospace_engineering_2027_v1.json"
PACK_PATH = PROGRAM_DIR / PACK_FILENAME
PROGRAM_REF = "program.uk.manchester.msc_aerospace_engineering"
EXPECTED_FILE_HASH = "876c906585c2892bf4849717e5ce3c985e33a4168afc92975caa624e2dd60acb"
EXPECTED_PACK_HASH = "b85dc0653cce1a767eb39541f4ee658669984bc8c5af71f1d46d9e9336ad0e97"
EXPECTED_SEMANTIC_HASH = (
    "975eea3fca34ea127c125bbc323703c420b802b766278e3acbe83a790427cd23"
)
MATRIX_PROGRAMS = (
    {
        "program_ref": PROGRAM_REF,
        "pack_filename": PACK_FILENAME,
        "primary_direction": "aerospace_engineering",
        "secondary_directions": [],
        "target_year_status": "2027_entry_explicit",
    },
    {
        "program_ref": "program.uk.manchester.msc_advanced_control_systems_engineering",
        "pack_filename": "manchester_msc_advanced_control_systems_engineering_2027_v1.json",
        "primary_direction": "low_altitude_economy",
        "secondary_directions": [],
        "target_year_status": "2027_entry_explicit",
    },
    {
        "program_ref": "program.uk.bristol.msc_aerospace_engineering",
        "pack_filename": "bristol_msc_aerospace_engineering_2027_v1.json",
        "primary_direction": "aerospace_engineering",
        "secondary_directions": [],
        "target_year_status": "current_official_page_2027_not_explicit",
    },
)
FROZEN_HASHES = {
    DATA_DIR / "manifest.json": "605d565eb217b5b7fa0bfe7fe1625a0a1a2aa45ccfad99887d63f01424f95bd8",
    PROGRAM_DIR / "hku_msc_computer_science_2027_v1.json": "781e0590367b98bc219bad9bd7a5401e11dbc7a6a60d03e615b47ebb5a87ddc5",
    PROGRAM_DIR / "hkust_msc_aeronautical_engineering_2027_v1.json": "0af8d6c39427be4ee0262362805b4b2b5b1ef64d16bb1dfc5750c2478861c945",
    PROGRAM_DIR / "hkust_msc_artificial_intelligence_2027_v1.json": "c3d67dfa5c99ddbbdbdad5d97e89c7424aa82c6d31120492a6a10c89dd567499",
    PROGRAM_DIR / "hkust_msc_information_technology_2027_v1.json": "18129395e8e3880aee7cb3941a039379f176b0267e1844b239ec8aefebbf382d",
    PROGRAM_DIR / "manchester_msc_advanced_computer_science_2027_v1.json": "b39c99188b2d02cb8ff0c8cbf3122a85995a9901908f5104de7b221fe91f9496",
}


class StableIds:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        count = self.counts.get(kind, 0) + 1
        self.counts[kind] = count
        return f"{kind}.phase4.batch8.7.test.{count}"


def _load_pack() -> AlphaProgramPackV1:
    return AlphaProgramPackV1.model_validate_json(PACK_PATH.read_text(encoding="utf-8"))


def _field(pack: AlphaProgramPackV1, field_key: str):
    return next(item for item in pack.candidate.fields if item.field_key == field_key)


def test_batch_8_7_splits_valid_aerospace_from_two_blocked_programs() -> None:
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

    assert PACK_FILENAME in actual_files
    assert MATRIX_PROGRAMS[1]["pack_filename"] not in actual_files
    assert MATRIX_PROGRAMS[2]["pack_filename"] not in actual_files

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


def test_batch_8_7_preserves_aerospace_fields_and_fail_closed_boundaries() -> None:
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
    assert intake.coverage_status == "confirmed"
    assert intake.value.intake_months == [9]

    application = _field(pack, "catalog.application_status").value_payload
    assert application.coverage_status == "confirmed"
    assert application.value.status == "open"
    assert application.value.opens_on is None
    assert application.value.closes_on is None

    primary = _field(pack, "taxonomy.primary_direction").value_payload
    secondary = _field(pack, "taxonomy.secondary_directions").value_payload
    assert primary.value.direction == "aerospace_engineering"
    assert secondary.value.directions == []

    academic = _field(pack, "requirements.academic").value_payload
    assert isinstance(academic, ProgramRequirementFieldV2)
    assert academic.coverage_status == "confirmed"
    assert academic.requirements[0].rule.operator == "manual_review"

    subject = _field(pack, "requirements.subject").value_payload
    assert isinstance(subject, ProgramRequirementFieldV2)
    subject_rule = subject.requirements[0].rule
    assert subject_rule.operator == "any"
    assert "aerospace_engineering" in subject_rule.children[0].accepted_values
    assert subject_rule.children[1].operator == "manual_review"

    prerequisite = _field(pack, "requirements.prerequisite_courses").value_payload
    language = _field(pack, "requirements.language").value_payload
    work = _field(pack, "requirements.work_experience").value_payload
    materials = _field(pack, "requirements.materials").value_payload
    assert prerequisite.coverage_status == "manual_review"
    assert prerequisite.requirements == []
    assert isinstance(language, ProgramRequirementFieldV2)
    assert len(language.requirements[0].rule.children) == 3
    assert work.coverage_status == "manual_review"
    assert materials.coverage_status == "manual_review"
    assert work.requirements == []
    assert materials.requirements == []

    for path, expected_hash in FROZEN_HASHES.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash


def test_batch_8_7_imports_one_candidate_idempotently_and_never_publishes(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'phase4-batch8-7.sqlite3'}"
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    scope = AlphaScopeSnapshotV1.model_validate_json(
        SCOPE_PATH.read_text(encoding="utf-8")
    )
    pack = _load_pack()
    importer = AlphaCandidateBatchImporter(
        sessions,
        clock=lambda: datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc),
        id_factory=StableIds(),
    )
    commands = [
        AlphaCandidateImportCommand(
            pack=pack,
            scope=scope,
            idempotency_key=f"phase4-batch8-7-{pack.pack_ref}",
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
