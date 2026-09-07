from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from backend.app.core.config import Settings
from backend.app.db.migrations import upgrade_database
from backend.app.db.models import ProgramPublication, ProgramVersion, SourceEvidence, VersionStatus
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.schemas.alpha_manifest import AlphaScopeSnapshotV1
from backend.app.schemas.alpha_program_pack import AlphaProgramPackV1
from backend.app.schemas.internal_alpha import InternalAlphaManifestV1
from backend.app.services.alpha_candidate_importer import AlphaCandidateImporter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "backend" / "data" / "alpha_v1"
FIXED_IMPORT_TIME = datetime(2026, 9, 4, 5, 30, tzinfo=timezone.utc)


class StableIds:
    def __init__(self, version_id: str, namespace: str) -> None:
        self.version_id = version_id
        self.namespace = namespace
        self.counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        if kind == "version":
            return self.version_id
        count = self.counts.get(kind, 0) + 1
        self.counts[kind] = count
        return f"{kind}.phase5.coverage.{self.namespace}.{count}"


def main() -> int:
    settings = Settings()
    batch = json.loads(
        (DATA_ROOT / "candidate_batches" / "coverage_2027_batch_v1.json").read_text(
            encoding="utf-8"
        )
    )
    scope = AlphaScopeSnapshotV1.model_validate_json(
        (DATA_ROOT / "scope_snapshot.json").read_text(encoding="utf-8")
    )
    manifest = InternalAlphaManifestV1.model_validate_json(
        (DATA_ROOT / "internal_manifest.json").read_text(encoding="utf-8")
    )
    additions = {item["pack_ref"] for item in batch["candidates"]}
    entries = [item for item in manifest.programs if item.pack_ref in additions]
    if len(entries) != 14:
        raise RuntimeError("internal manifest must contain all 14 reviewed additions")

    upgrade_database(settings.database_url)
    engine = create_database_engine(settings.database_url)
    sessions = create_session_factory(engine)
    results = []
    for index, entry in enumerate(entries, start=1):
        pack = AlphaProgramPackV1.model_validate_json(
            (DATA_ROOT / entry.pack_path).read_text(encoding="utf-8")
        )
        with sessions.begin() as session:
            result = AlphaCandidateImporter(
                session,
                clock=lambda: FIXED_IMPORT_TIME,
                id_factory=StableIds(entry.candidate_version_id, f"{index:02d}"),
            ).import_pack(
                pack=pack,
                scope=scope,
                idempotency_key=f"phase5-coverage-{pack.pack_ref}",
            )
        results.append(result)

    program_refs = [entry.program_ref for entry in entries]
    version_ids = [entry.candidate_version_id for entry in entries]
    with sessions.begin() as session:
        versions = session.scalars(
            select(ProgramVersion).where(ProgramVersion.id.in_(version_ids))
        ).all()
        evidence_count = int(
            session.scalar(
                select(func.count())
                .select_from(SourceEvidence)
                .where(SourceEvidence.program_id.in_(program_refs))
            )
            or 0
        )
        publication_count = int(
            session.scalar(
                select(func.count())
                .select_from(ProgramPublication)
                .where(ProgramPublication.program_id.in_(program_refs))
            )
            or 0
        )
    expected_evidence = sum(
        len(
            AlphaProgramPackV1.model_validate_json(
                (DATA_ROOT / entry.pack_path).read_text(encoding="utf-8")
            ).evidence
        )
        for entry in entries
    )
    valid = (
        len(results) == 14
        and len(versions) == 14
        and all(version.status == VersionStatus.CANDIDATE for version in versions)
        and evidence_count == expected_evidence
        and publication_count == 0
    )
    print(
        json.dumps(
            {
                "valid": valid,
                "dataset_id": manifest.dataset_id,
                "imported_program_count": len(results),
                "candidate_version_count": len(versions),
                "evidence_count": evidence_count,
                "publication_count": publication_count,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    engine.dispose()
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
