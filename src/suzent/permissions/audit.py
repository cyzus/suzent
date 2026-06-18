from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from suzent.logger import get_logger

logger = get_logger(__name__)

_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
}
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"(?i)\b(bearer\s+)[^\s\"']+"),
    re.compile(r"(?i)\b(api[_-]?key|password|secret|token)\s*[:=]\s*([^\s,;]+)"),
)


def _sanitize_text(value: str) -> str:
    sanitized = value
    for pattern in _SENSITIVE_VALUE_PATTERNS:
        if pattern.pattern.lower().find("bearer") >= 0:
            sanitized = pattern.sub(r"\1[redacted]", sanitized)
        else:
            sanitized = pattern.sub(r"\1=[redacted]", sanitized)
    return sanitized if len(sanitized) <= 300 else sanitized[:300] + "…"


def _sanitize_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 3:
        return "[truncated]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, nested in list(value.items())[:20]:
            key_text = str(key)
            normalized = key_text.lower().replace("-", "_")
            result[key_text] = (
                "[redacted]"
                if any(sensitive in normalized for sensitive in _SENSITIVE_KEYS)
                else _sanitize_value(nested, depth=depth + 1)
            )
        return result
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item, depth=depth + 1) for item in value[:20]]
    return _sanitize_text(str(value))


def sanitize_args(args: dict[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize_value(args)
    return sanitized if isinstance(sanitized, dict) else {}


def record_permission_audit(
    *,
    chat_id: str,
    tool_call_id: str,
    tool_name: str,
    args: dict[str, Any],
    decision: str,
    reason: str,
    reason_code: str,
    mode: str,
    run_id: str | None = None,
    user_action: str | None = None,
    feedback: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        from suzent.config import USER_CONFIG_DIR

        path = Path(USER_CONFIG_DIR) / "permission-audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "chat_id": chat_id,
            "run_id": run_id,
            "tool_call_id": tool_call_id,
            "tool": tool_name,
            "args": sanitize_args(args),
            "decision": decision,
            "reason": reason,
            "reason_code": reason_code,
            "mode": mode,
            "user_action": user_action,
            "feedback": feedback[:500] if feedback else None,
            "metadata": sanitize_args(metadata or {}),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Failed to record permission audit event: {}", exc)
