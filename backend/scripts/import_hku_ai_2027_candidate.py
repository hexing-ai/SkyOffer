from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select

from backend.app.core.config import Settings
from backend.app.db.migrations import upgrade_database
from backend.app.db.models import ProgramPublication, ProgramVersion, VersionStatus
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.services.alpha_candidate_importer import AlphaCandidateImporter
from backend.app.services.internal_alpha_quality import (
    InternalAlphaQualityScanner,
    load_internal_alpha_quality_context,
)
from backend.scripts.refresh_hku_ai_2027_candidate import (
    DATA_ROOT,
    PACK_REF,
    PROGRAM_REF,
    VERSION_ID,
)


FIXED_NOW = datetime(2026, 9, 4, 8, 5, tzinfo=UTC)


class StableIds:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        if kind == "version":
            return VERSION_ID
        count = self.counts.get(kind, 0) + 1
        self.counts[kind] = count
        return f"{kind}.hku.mscai.2027.refresh.{count}"


def main() -> int:
    settings = Settings()
    upgrade_database(settings.database_url)
    engine = create_database_engine(settings.database_url)
    sessions = create_session_factory(engine)
    context = load_internal_alpha_quality_context(
        root=DATA_ROOT, generated_commit="hku-ai-2027-refresh"
    )
    entry = next(item for item in context.manifest.programs if item.pack_ref == PACK_REF)
    pack = context.packs_by_ref[PACK_REF]

    with sessions.begin() as session:
        result = AlphaCandidateImporter(
            session,
            clock=lambda: FIXED_NOW,
            id_factory=StableIds(),
        ).import_pack(
            pack=pack,
            scope=context.scope,
            idempotency_key="hku-ai-2027-refresh-v1",
        )

    with sessions.begin() as session:
        report = InternalAlphaQualityScanner(
            session, clock=lambda: FIXED_NOW
        ).scan(context)
        version = session.get(ProgramVersion, VERSION_ID)
        publication = session.get(ProgramPublication, PROGRAM_REF)
        candidate_versions = session.scalars(
            select(ProgramVersion).where(
                ProgramVersion.program_id == PROGRAM_REF,
                ProgramVersion.status == VersionStatus.CANDIDATE,
            )
        ).all()

    valid = (
        result.candidate_version_id == entry.candidate_version_id == VERSION_ID
        and version is not None
        and version.content_sha256 == pack.expected_semantic_content_sha256
        and publication is None
        and report.ready_for_internal_mvp
    )
    print(
        json.dumps(
            {
                "valid": valid,
                "dataset_id": context.manifest.dataset_id,
                "candidate_version_id": VERSION_ID,
                "candidate_version_count_for_program": len(candidate_versions),
                "publication_count_for_program": int(publication is not None),
                "quality_ready": report.ready_for_internal_mvp,
                "blocking_gates": report.blocking_gates,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    engine.dispose()
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
