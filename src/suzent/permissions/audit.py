from __future__ import annotations

import asyncio
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
# Each entry pairs a compiled pattern with its replacement template so the
# substitution intent lives with the pattern instead of being re-derived per
# call by substring-searching the regex source.
_SENSITIVE_VALUE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\b(bearer\s+)[^\s\"']+"), r"\1[redacted]"),
    (
        re.compile(r"(?i)\b(api[_-]?key|password|secret|token)\s*[:=]\s*([^\s,;]+)"),
        r"\1=[redacted]",
    ),
)


def _sanitize_text(value: str) -> str:
    sanitized = value
    for pattern, replacement in _SENSITIVE_VALUE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
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


def _write_audit_event(event: dict[str, Any]) -> None:
    try:
        from suzent.config import USER_CONFIG_DIR

        path = Path(USER_CONFIG_DIR) / "permission-audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Failed to record permission audit event: {}", exc)


async def record_permission_audit(
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
    # Offload the blocking filesystem append so it never stalls the event loop
    # (and thus token streaming for all chats sharing it) on the hot path.
    await asyncio.to_thread(_write_audit_event, event)
