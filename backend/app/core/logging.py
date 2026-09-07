from __future__ import annotations

import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def __init__(self, app_version: str) -> None:
        super().__init__()
        self.app_version = app_version

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "version": self.app_version,
        }
        for key in ("request_id", "method", "path", "status_code", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(
    level: str = "INFO",
    log_format: str = "text",
    app_version: str = "local",
) -> logging.Logger:
    logger = logging.getLogger("skyoffer")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        logger.addHandler(handler)
    formatter = (
        JsonFormatter(app_version)
        if log_format == "json"
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    for handler in logger.handlers:
        handler.setFormatter(formatter)
    return logger
