from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.models import Program, ProgramPublication, VersionStatus
from backend.app.repositories.candidates import CandidateRepository
from backend.app.repositories.evidence import SourceEvidenceRepository
from backend.app.repositories.idempotency import IdempotencyExecutor
from backend.app.repositories.programs import ProgramRepository
from backend.app.schemas.alpha_import import (
    AlphaCandidateBatchImportReport,
    AlphaCandidateBatchItemResult,
    AlphaCandidateImportResult,
)
from backend.app.schemas.alpha_manifest import AlphaScopeSnapshotV1
from backend.app.schemas.alpha_program_pack import AlphaProgramPackV1
from backend.app.schemas.candidates import CandidateCreate
from backend.app.schemas.evidence import SourceEvidenceCreateV2
from backend.app.schemas.programs import ProgramCreateRequest
from backend.app.services.alpha_program_pack_validator import (
    validate_alpha_program_pack,
)


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]


class AlphaCandidateImportError(RuntimeError):
    pass


class AlphaProgramIdentityConflictError(AlphaCandidateImportError):
    pass


class AlphaImportedContentMismatchError(AlphaCandidateImportError):
    pass


class AlphaPublicationBoundaryError(AlphaCandidateImportError):
    pass


@dataclass(frozen=True, slots=True)
class AlphaCandidateImportCommand:
    pack: AlphaProgramPackV1
    scope: AlphaScopeSnapshotV1
    idempotency_key: str


class AlphaCandidateImporter:
    """Import one validated Pack as Program/Evidence/candidate, never as published."""

    OPERATION_TYPE = "alpha.candidate_import"

    def __init__(
        self,
        session: Session,
        *,
        clock: Clock,
        id_factory: IdFactory,
    ) -> None:
        self._session = session
        self._clock = clock
        self._id_factory = id_factory

    def import_pack(
        self,
        *,
        pack: AlphaProgramPackV1,
        scope: AlphaScopeSnapshotV1,
        idempotency_key: str,
    ) -> AlphaCandidateImportResult:
        validate_alpha_program_pack(pack=pack, scope=scope)
        return IdempotencyExecutor(
            self._session,
            clock=self._clock,
            id_factory=self._id_factory,
        ).execute(
            key=idempotency_key,
            operation_type=self.OPERATION_TYPE,
            request_payload={
                "schema_version": pack.schema_version,
                "pack_ref": pack.pack_ref,
                "pack_canonical_sha256": pack.pack_canonical_sha256,
                "expected_semantic_content_sha256": (
                    pack.expected_semantic_content_sha256
                ),
                "scope_snapshot_id": pack.scope_snapshot_id,
                "scope_canonical_sha256": scope.canonical_sha256,
            },
            response_model=AlphaCandidateImportResult,
            handler=lambda: self._create_candidate_only(pack),
            response_status=201,
        )

    def _create_candidate_only(
        self, pack: AlphaProgramPackV1
    ) -> AlphaCandidateImportResult:
        program, program_created = self._ensure_program(pack)
        publication_before = self._session.get(ProgramPublication, program.id)
        current_version_id = (
            publication_before.current_version_id
            if publication_before is not None
            else None
        )

        evidence_repository = SourceEvidenceRepository(
            self._session, clock=self._clock
        )
        for evidence in pack.evidence:
            evidence_repository.create(
                SourceEvidenceCreateV2.model_validate(
                    evidence.model_dump(
                        mode="python", exclude={"applicable_academic_year"}
                    )
                )
            )

        candidate_payload = CandidateCreate(
            base_version_id=current_version_id,
            fields=pack.candidate.fields,
            created_by=pack.candidate.created_by,
            creation_note=pack.candidate.creation_note,
            request_id=pack.candidate.request_id,
        )
        candidate = CandidateRepository(
            self._session,
            clock=self._clock,
            id_factory=self._id_factory,
        ).create(program.id, candidate_payload)
        if candidate.status != VersionStatus.CANDIDATE:
            raise AlphaPublicationBoundaryError(
                "Alpha importer may only create candidate versions."
            )
        if candidate.content_sha256 != pack.expected_semantic_content_sha256:
            raise AlphaImportedContentMismatchError(
                "Imported candidate semantic hash does not match the frozen Pack."
            )

        publication_after = self._session.get(ProgramPublication, program.id)
        current_after = (
            publication_after.current_version_id
            if publication_after is not None
            else None
        )
        if current_after != current_version_id:
            raise AlphaPublicationBoundaryError(
                "Alpha importer changed the publication pointer."
            )

        return AlphaCandidateImportResult(
            schema_version="alpha_candidate_import_result.v1",
            pack_ref=pack.pack_ref,
            pack_canonical_sha256=pack.pack_canonical_sha256,
            program_id=program.id,
            program_created=program_created,
            evidence_ids=[item.id for item in pack.evidence],
            candidate_version_id=candidate.id,
            candidate_version_no=candidate.version_no,
            candidate_status="candidate",
            candidate_content_sha256=candidate.content_sha256,
            publication_current_version_id=current_after,
            request_id=pack.candidate.request_id,
        )

    def _ensure_program(self, pack: AlphaProgramPackV1) -> tuple[Program, bool]:
        program_ref = pack.program.program_ref
        existing = self._session.get(Program, program_ref)
        same_url = self._session.scalar(
            select(Program).where(
                Program.official_program_url == pack.program.official_program_url
            )
        )
        if existing is not None:
            if same_url is not None and same_url.id != existing.id:
                raise AlphaProgramIdentityConflictError(
                    "Official Program URL belongs to another Program ID."
                )
            expected = (
                pack.program.official_name,
                pack.program.institution_name,
                pack.program.region.value,
                pack.program.official_program_url,
                pack.program.registered_official_domain,
                pack.program.official_domain_aliases,
            )
            actual = (
                existing.official_name,
                existing.institution_name,
                str(existing.region),
                existing.official_program_url,
                existing.registered_official_domain,
                existing.official_domain_aliases,
            )
            if actual != expected:
                raise AlphaProgramIdentityConflictError(
                    "Pack Program identity conflicts with the existing Program."
                )
            return existing, False
        if same_url is not None:
            raise AlphaProgramIdentityConflictError(
                "Official Program URL belongs to another Program ID."
            )

        payload = ProgramCreateRequest(
            official_name=pack.program.official_name,
            institution_name=pack.program.institution_name,
            region=pack.program.region,
            official_program_url=pack.program.official_program_url,
            registered_official_domain=pack.program.registered_official_domain,
            official_domain_aliases=pack.program.official_domain_aliases,
            created_by=pack.program.created_by,
            creation_note=pack.program.creation_note,
        )

        def stable_program_id(kind: str) -> str:
            return program_ref if kind == "program" else self._id_factory(kind)

        record = ProgramRepository(
            self._session,
            clock=self._clock,
            id_factory=stable_program_id,
        ).create(payload, request_id=pack.candidate.request_id)
        program = self._session.get(Program, record.id)
        if program is None or program.id != program_ref:
            raise AlphaCandidateImportError(
                "Program repository did not preserve the Pack Program ref."
            )
        return program, True


class AlphaCandidateBatchImporter:
    """Run each Pack in its own transaction and report partial batch outcomes."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        clock: Clock,
        id_factory: IdFactory,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._id_factory = id_factory

    def import_commands(
        self, commands: Iterable[AlphaCandidateImportCommand]
    ) -> AlphaCandidateBatchImportReport:
        command_list = list(commands)
        if not command_list:
            raise ValueError("candidate import batch cannot be empty")
        pack_refs = [command.pack.pack_ref for command in command_list]
        if len(pack_refs) != len(set(pack_refs)):
            raise ValueError("candidate import batch pack refs must be unique")
        items: list[AlphaCandidateBatchItemResult] = []
        for command in command_list:
            try:
                with self._session_factory.begin() as session:
                    result = AlphaCandidateImporter(
                        session,
                        clock=self._clock,
                        id_factory=self._id_factory,
                    ).import_pack(
                        pack=command.pack,
                        scope=command.scope,
                        idempotency_key=command.idempotency_key,
                    )
                items.append(
                    AlphaCandidateBatchItemResult(
                        pack_ref=command.pack.pack_ref,
                        status="imported",
                        result=result,
                        error_code=None,
                        error_message=None,
                    )
                )
            except Exception:
                items.append(
                    AlphaCandidateBatchItemResult(
                        pack_ref=command.pack.pack_ref,
                        status="failed",
                        result=None,
                        error_code="ALPHA_IMPORT_FAILED",
                        error_message="Candidate-only import failed and was rolled back.",
                    )
                )
        imported_count = sum(item.status == "imported" for item in items)
        failed_count = len(items) - imported_count
        return AlphaCandidateBatchImportReport(
            schema_version="alpha_candidate_batch_import_report.v1",
            attempted_count=len(items),
            imported_count=imported_count,
            failed_count=failed_count,
            complete=failed_count == 0,
            items=items,
        )
