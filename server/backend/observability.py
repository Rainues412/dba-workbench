"""Request context, structured logging, redaction, and minimal audit writes."""

from __future__ import annotations

import contextvars
import json
import logging
import re
from datetime import datetime, timezone

from backend.database import get_db_ctx


request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)

_SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|token|secret|authorization|ciphertext|password_enc)"
    r"(\s*[:=]\s*|\s+)([^\s,;]+)"
)


def redact(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SECRET_PATTERN.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    return value


class JsonFormatter(logging.Formatter):
    """Small JSON formatter that redacts secret-shaped values."""

    _FIELDS = ("event", "request_id", "method", "path", "status_code", "duration_ms")

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        for field in self._FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = redact(value)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("dba")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


logger = configure_logging()


def record_audit(
    *,
    action: str,
    object_type: str,
    object_id: str = "",
    result: str,
    source: str,
    actor: str = "local-user",
    request_id: str | None = None,
) -> None:
    """Persist metadata only. Callers cannot attach arbitrary secret-bearing details."""
    rid = request_id if request_id is not None else request_id_var.get()
    with get_db_ctx() as conn:
        conn.execute(
            """INSERT INTO audit_events
               (request_id, actor, action, object_type, object_id, result, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (rid or "system", actor, action, object_type, object_id, result, source),
        )
        conn.commit()
