from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    normalized = value.normalize()
    return format(normalized, "f")


def normalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return normalize(value.model_dump(mode="python", exclude_none=False))
    if isinstance(value, Enum):
        return normalize(value.value)
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime values must include a timezone")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        return {
            str(normalize(key)): normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (set, frozenset)):
        normalized = [normalize(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, ensure_ascii=False))
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
