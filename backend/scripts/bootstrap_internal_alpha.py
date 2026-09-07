from __future__ import annotations

import hashlib
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
from backend.app.services.selection_advice import DEFAULT_ALPHA_ROOT


class StableBootstrapIds:
    def __init__(self, *, version_id: str, pack_ref: str) -> None:
        self.version_id = version_id
        self.namespace = hashlib.sha256(pack_ref.encode("utf-8")).hexdigest()[:12]
        self.counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        if kind == "version":
            return self.version_id
        count = self.counts.get(kind, 0) + 1
        self.counts[kind] = count
        return f"{kind}.bootstrap.{self.namespace}.{count}"


def bootstrap_internal_alpha(settings: Settings) -> dict[str, object]:
    settings.assert_runtime_ready()
    upgrade_database(settings.database_url)
    engine = create_database_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )
    sessions = create_session_factory(engine)
    context = load_internal_alpha_quality_context(
        root=DEFAULT_ALPHA_ROOT,
        generated_commit=settings.app_version,
    )
    imported = 0
    reused = 0
    now = datetime.now(UTC)
    try:
        for entry in context.manifest.programs:
            with sessions.begin() as session:
                existing = session.get(ProgramVersion, entry.candidate_version_id)
                if existing is not None:
                    if (
                        existing.program_id != entry.program_ref
                        or existing.status != VersionStatus.CANDIDATE
                        or existing.content_sha256 != entry.candidate_semantic_sha256
                    ):
                        raise RuntimeError(
                            f"candidate version conflicts with manifest: {entry.candidate_version_id}"
                        )
                    reused += 1
                    continue
                pack = context.packs_by_ref[entry.pack_ref]
                AlphaCandidateImporter(
                    session,
                    clock=lambda: now,
                    id_factory=StableBootstrapIds(
                        version_id=entry.candidate_version_id,
                        pack_ref=entry.pack_ref,
                    ),
                ).import_pack(
                    pack=pack,
                    scope=context.scope,
                    idempotency_key=(
                        f"bootstrap-{entry.pack_canonical_sha256}"
                    ),
                )
                imported += 1

        with sessions.begin() as session:
            report = InternalAlphaQualityScanner(
                session,
                clock=lambda: now,
            ).scan(context)
            publication_count = len(
                session.scalars(select(ProgramPublication)).all()
            )
        if not report.ready_for_internal_mvp or publication_count:
            raise RuntimeError("internal Alpha production bootstrap failed quality gates")
        return {
            "valid": True,
            "dataset_id": context.manifest.dataset_id,
            "program_count": report.program_count,
            "imported": imported,
            "reused": reused,
            "publication_count": publication_count,
        }
    finally:
        engine.dispose()


def main() -> int:
    result = bootstrap_internal_alpha(Settings())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
