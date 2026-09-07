from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from backend.app.core.config import Settings
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


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "backend" / "data" / "alpha_v1"
PACK_PATH = DATA_DIR / "programs" / "manchester_msc_aerospace_engineering_2027_v1.json"
FIXED_IMPORT_TIME = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)


class StableIds:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        count = self._counts.get(kind, 0) + 1
        self._counts[kind] = count
        return f"{kind}.phase4.batch8.7.{count}"


def main() -> int:
    settings = Settings()
    scope = AlphaScopeSnapshotV1.model_validate_json(
        (DATA_DIR / "scope_snapshot.json").read_text(encoding="utf-8")
    )
    pack = AlphaProgramPackV1.model_validate_json(
        PACK_PATH.read_text(encoding="utf-8")
    )
    upgrade_database(settings.database_url)
    engine = create_database_engine(settings.database_url)
    sessions = create_session_factory(engine)
    report = AlphaCandidateBatchImporter(
        sessions,
        clock=lambda: FIXED_IMPORT_TIME,
        id_factory=StableIds(),
    ).import_commands(
        [
            AlphaCandidateImportCommand(
                pack=pack,
                scope=scope,
                idempotency_key=f"phase4-batch8-7-{pack.pack_ref}",
            )
        ]
    )

    with sessions.begin() as session:
        programs = int(
            session.scalar(
                select(func.count())
                .select_from(Program)
                .where(Program.id == pack.program.program_ref)
            )
            or 0
        )
        evidence = int(
            session.scalar(
                select(func.count())
                .select_from(SourceEvidence)
                .where(SourceEvidence.program_id == pack.program.program_ref)
            )
            or 0
        )
        versions = session.scalars(
            select(ProgramVersion).where(
                ProgramVersion.program_id == pack.program.program_ref
            )
        ).all()
        version_ids = [version.id for version in versions]
        fields = int(
            session.scalar(
                select(func.count())
                .select_from(ProgramFieldValue)
                .where(ProgramFieldValue.program_version_id.in_(version_ids))
            )
            or 0
        )
        publications = int(
            session.scalar(
                select(func.count())
                .select_from(ProgramPublication)
                .where(ProgramPublication.program_id == pack.program.program_ref)
            )
            or 0
        )

    postconditions = {
        "programs": programs,
        "evidence": evidence,
        "candidate_versions": len(versions),
        "fields": fields,
        "publications": publications,
        "all_versions_candidate": all(
            version.status == VersionStatus.CANDIDATE for version in versions
        ),
        "semantic_hashes_match": {
            version.content_sha256 for version in versions
        }
        == {pack.expected_semantic_content_sha256},
    }
    valid = report.complete and postconditions == {
        "programs": 1,
        "evidence": 4,
        "candidate_versions": 1,
        "fields": 15,
        "publications": 0,
        "all_versions_candidate": True,
        "semantic_hashes_match": True,
    }
    print(
        json.dumps(
            {
                "valid": valid,
                "database_url": settings.database_url,
                "batch_report": report.model_dump(mode="json"),
                "postconditions": postconditions,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    engine.dispose()
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
