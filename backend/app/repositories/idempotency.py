from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import event, select
from sqlalchemy.orm import Session, object_session

from backend.app.db.models import IdempotencyRecord
from backend.app.rules.canonical import content_hash, normalize
from backend.app.schemas.evidence import normalize_aware_utc


ResponseModel = TypeVar("ResponseModel", bound=BaseModel)
Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]
SESSION_KEY_HASH = "phase3_idempotency_key_hash"


class IdempotencyError(RuntimeError):
    pass


class IdempotencyKeyInvalidError(IdempotencyError):
    pass


class IdempotencyConflictError(IdempotencyError):
    pass


class IdempotencyRecordImmutableError(IdempotencyError):
    pass


@event.listens_for(IdempotencyRecord, "before_update", propagate=True)
def _reject_idempotency_update(_mapper, _connection, target) -> None:
    session = object_session(target)
    if session is None or session.is_modified(target, include_collections=False):
        raise IdempotencyRecordImmutableError("幂等记录创建后不可修改。")


@event.listens_for(IdempotencyRecord, "before_delete", propagate=True)
def _reject_idempotency_delete(_mapper, _connection, _target) -> None:
    raise IdempotencyRecordImmutableError("幂等记录不可删除。")


def current_idempotency_key_hash(session: Session) -> str | None:
    value = session.info.get(SESSION_KEY_HASH)
    return value if isinstance(value, str) else None


def _validate_key(value: str) -> str:
    if not isinstance(value, str):
        raise IdempotencyKeyInvalidError("Idempotency key 必须是字符串。")
    if not 16 <= len(value) <= 200:
        raise IdempotencyKeyInvalidError("Idempotency key 长度必须为 16–200。")
    if value != value.strip() or any(ord(character) < 32 for character in value):
        raise IdempotencyKeyInvalidError("Idempotency key 格式无效。")
    return value


def _validate_operation_type(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{1,79}", value):
        raise IdempotencyKeyInvalidError("operation_type 格式无效。")
    return value


class IdempotencyExecutor:
    def __init__(self, session: Session, *, clock: Clock, id_factory: IdFactory) -> None:
        self._session = session
        self._clock = clock
        self._id_factory = id_factory

    def execute(
        self,
        *,
        key: str,
        operation_type: str,
        request_payload: object,
        response_model: type[ResponseModel],
        handler: Callable[[], ResponseModel],
        response_status: int = 200,
    ) -> ResponseModel:
        raw_key = _validate_key(key)
        operation = _validate_operation_type(operation_type)
        if not 100 <= response_status <= 599:
            raise ValueError("response_status must be between 100 and 599")
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        request_sha256 = content_hash(
            {"operation_type": operation, "request": request_payload}
        )
        existing = self._session.scalar(
            select(IdempotencyRecord).where(IdempotencyRecord.key_hash == key_hash)
        )
        if existing is not None:
            return self._replay(
                existing,
                operation_type=operation,
                request_sha256=request_sha256,
                response_model=response_model,
            )

        previous_hash = self._session.info.get(SESSION_KEY_HASH)
        try:
            with self._session.begin_nested():
                self._session.info[SESSION_KEY_HASH] = key_hash
                response = response_model.model_validate(handler())
                response_body = normalize(response)
                self._session.add(
                    IdempotencyRecord(
                        id=self._id_factory("idempotency"),
                        key_hash=key_hash,
                        operation_type=operation,
                        request_sha256=request_sha256,
                        response_status=response_status,
                        response_body=response_body,
                        created_at=normalize_aware_utc(self._clock()),
                    )
                )
                self._session.flush()
        finally:
            if previous_hash is None:
                self._session.info.pop(SESSION_KEY_HASH, None)
            else:
                self._session.info[SESSION_KEY_HASH] = previous_hash
        return response_model.model_validate(response_body)

    @staticmethod
    def _replay(
        record: IdempotencyRecord,
        *,
        operation_type: str,
        request_sha256: str,
        response_model: type[ResponseModel],
    ) -> ResponseModel:
        if (
            record.operation_type != operation_type
            or record.request_sha256 != request_sha256
        ):
            raise IdempotencyConflictError(
                "同一 Idempotency key 已用于不同请求。"
            )
        return response_model.model_validate(record.response_body)
