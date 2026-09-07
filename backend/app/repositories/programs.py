from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import ActorRole, AuditEvent, AuditEventType, Program
from backend.app.repositories.idempotency import current_idempotency_key_hash
from backend.app.schemas.evidence import normalize_aware_utc
from backend.app.schemas.programs import ProgramCreateRequest, ProgramRecord


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]


class ProgramRepositoryError(RuntimeError):
    pass


class ProgramAlreadyExistsError(ProgramRepositoryError):
    pass


class ProgramRepository:
    def __init__(self, session: Session, *, clock: Clock, id_factory: IdFactory) -> None:
        self._session = session
        self._clock = clock
        self._id_factory = id_factory

    def create(
        self, payload: ProgramCreateRequest, *, request_id: str
    ) -> ProgramRecord:
        existing = self._session.scalar(
            select(Program).where(
                Program.official_program_url == payload.official_program_url
            )
        )
        if existing is not None:
            raise ProgramAlreadyExistsError(
                "Official program URL 已登记为另一个 Program。"
            )
        now = normalize_aware_utc(self._clock())
        program = Program(
            id=self._id_factory("program"),
            official_name=payload.official_name,
            institution_name=payload.institution_name,
            region=payload.region,
            official_program_url=payload.official_program_url,
            registered_official_domain=payload.registered_official_domain,
            official_domain_aliases=payload.official_domain_aliases,
            created_at=now,
        )
        self._session.add(program)
        self._session.add(
            AuditEvent(
                id=self._id_factory("audit"),
                program_id=program.id,
                version_id=None,
                event_type=AuditEventType.CREATE,
                actor_ref=payload.created_by,
                actor_role=ActorRole.DATA_PREPARER,
                reason=payload.creation_note,
                request_id=request_id,
                idempotency_key_hash=current_idempotency_key_hash(self._session),
                event_payload={
                    "entity_type": "program",
                    "official_name": payload.official_name,
                    "institution_name": payload.institution_name,
                },
                created_at=now,
            )
        )
        self._session.flush()
        return ProgramRecord(
            id=program.id,
            official_name=program.official_name,
            institution_name=program.institution_name,
            region=program.region,
            official_program_url=program.official_program_url,
            registered_official_domain=program.registered_official_domain,
            official_domain_aliases=list(program.official_domain_aliases),
            created_by=payload.created_by,
            created_at=program.created_at,
        )
