from __future__ import annotations

import json
import logging
from typing import Any


logger = logging.getLogger("security.audit")

def _safe_value(value: Any, max_length: int = 128) -> str | None:
    if value is None:
        return None
    text = "".join(" " if ord(char) < 32 or ord(char) == 127 else char for char in str(value))
    text = " ".join(text.split())
    return text[:max_length] or None


def audit_security_event(
    event: str,
    *,
    session_id: str | None = None,
    client_ip: str | None = None,
    resource_id: str | None = None,
    reason: str | None = None,
) -> None:
    """Write a small, structured security event without credentials or user content."""
    try:
        record = {
            "event": _safe_value(event, 64),
            "session_id": _safe_value(session_id, 64),
            "client_ip": _safe_value(client_ip, 64),
            "resource_id": _safe_value(resource_id, 64),
            "reason": _safe_value(reason, 128),
        }
        logger.warning("security_audit %s", json.dumps(record, ensure_ascii=True, separators=(",", ":")))
    except Exception:
        # Audit logging must never take down the protected business request.
        return
