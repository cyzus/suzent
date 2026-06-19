"""Permission policy management endpoints."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.config import CONFIG, PROJECT_DIR, USER_CONFIG_DIR
from suzent.core.agent_serializer import deserialize_state
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.permissions.loader import (
    delete_global_permission_rule,
    upsert_permission_rule,
)
from suzent.permissions.actions import build_approval_decision
from suzent.permissions.models import PermissionRule
from suzent.permissions.rules import parse_rules

logger = get_logger(__name__)


def _unanswered_tool_call_ids(agent_state: bytes | None) -> set[str] | None:
    """Return unanswered call IDs, or None when persisted state is unavailable."""
    if not agent_state:
        return None
    state = deserialize_state(agent_state)
    if not state:
        return None

    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        ToolCallPart,
        ToolReturnPart,
    )

    history = state.get("message_history") or []
    answered = {
        part.tool_call_id
        for message in history
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_call_id
    }
    return {
        part.tool_call_id
        for message in history
        if isinstance(message, ModelResponse)
        for part in message.parts
        if (
            isinstance(part, ToolCallPart)
            and part.tool_call_id
            and part.tool_call_id not in answered
        )
    }


def _serialized_rules(raw_rules: Any) -> list[dict[str, Any]]:
    return [
        rule.model_dump(mode="json", by_alias=True) for rule in parse_rules(raw_rules)
    ]


def _session_rules(chat_id: str | None) -> tuple[list[dict[str, Any]], bool]:
    if not chat_id:
        return [], True
    chat = get_database().get_chat(chat_id)
    if chat is None:
        return [], False
    return _serialized_rules((chat.config or {}).get("permission_rules")), True


async def get_permissions(request: Request) -> JSONResponse:
    """Return global and optional per-chat permission rules."""

    chat_id = request.query_params.get("chat_id")
    session_rules, chat_exists = _session_rules(chat_id)
    if not chat_exists:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    global_rules = _serialized_rules(CONFIG.permission_rules)
    return JSONResponse(
        {
            "globalRules": global_rules,
            "sessionRules": session_rules,
            "effectiveRules": [*global_rules, *session_rules],
            "legacyPolicies": CONFIG.permission_policies,
        }
    )


async def get_chat_permission_state(request: Request) -> JSONResponse:
    """Return the mode and exact pending approval contracts for one chat."""

    chat_id = str(request.path_params["chat_id"])
    chat = get_database().get_chat(chat_id)
    if chat is None:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    config = dict(chat.config or {})
    stored_pending = config.get("_pending_approvals") or []
    unanswered_ids = _unanswered_tool_call_ids(getattr(chat, "agent_state", None))
    if unanswered_ids is not None:
        # Prune answered approvals under the per-chat approval lock so this
        # read-modify-write cannot race a concurrent stream writer (which
        # appends a newly-suspended approval via the same lock) and drop it.
        from suzent.streaming import _get_approval_lock

        def _prune() -> list[dict[str, Any]]:
            db = get_database()
            current_chat = db.get_chat(chat_id)
            current = (
                (current_chat.config or {}).get("_pending_approvals") or []
                if current_chat is not None
                else []
            )
            filtered = [
                item
                for item in current
                if isinstance(item, dict)
                and str(item.get("toolCallId") or item.get("approvalId") or "")
                in unanswered_ids
            ]
            if filtered != current:
                db.merge_chat_config(chat_id, {"_pending_approvals": filtered})
            return filtered

        async with _get_approval_lock(chat_id):
            stored_pending = await asyncio.to_thread(_prune)

    pending: list[dict[str, Any]] = []
    for item in stored_pending:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision")
        if not isinstance(decision, dict) or not decision.get("actions"):
            generated = build_approval_decision(
                str(item.get("toolName") or "unknown"),
                item.get("args") if isinstance(item.get("args"), dict) else {},
                reason="This restored tool call requires approval",
                reason_code="restored_legacy_approval",
            ).model_dump(mode="json", by_alias=True)
            generated["actions"] = [
                action
                for action in generated["actions"]
                if action.get("scope") == "once"
            ]
            decision = generated
        pending.append({**item, "decision": decision})

    mode = str(config.get("permission_mode") or "default")
    pre_plan_mode = config.get("pre_plan_permission_mode")
    return JSONResponse(
        {
            "chatId": chat_id,
            "mode": mode,
            "prePlanMode": pre_plan_mode,
            "pendingApprovals": pending,
        }
    )


async def create_permission_rule(request: Request) -> JSONResponse:
    """Create a normalized global or per-chat permission rule."""

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    destination = str(data.get("destination") or "").strip().lower()
    if destination not in {"global", "session"}:
        return JSONResponse(
            {"error": "destination must be global or session"},
            status_code=400,
        )
    raw_rule = data.get("rule")
    if not isinstance(raw_rule, dict):
        raw_rule = {
            key: value
            for key, value in data.items()
            if key not in {"destination", "chat_id", "chatId"}
        }
    try:
        rule = PermissionRule.model_validate(
            {
                **raw_rule,
                "source": destination,
            }
        )
    except ValidationError as exc:
        return JSONResponse(
            {"error": "Invalid permission rule", "details": exc.errors()},
            status_code=422,
        )

    chat_id: str | None = None
    db = None
    if destination == "session":
        chat_id = str(data.get("chat_id") or data.get("chatId") or "").strip()
        if not chat_id:
            return JSONResponse(
                {"error": "chat_id is required for session rules"},
                status_code=400,
            )
        db = get_database()
        if db.get_chat(chat_id) is None:
            return JSONResponse({"error": "Chat not found"}, status_code=404)

    upsert_permission_rule(
        rule,
        destination=destination,
        project_dir=PROJECT_DIR,
        logger=logger,
        config=CONFIG,
        database=db,
        chat_id=chat_id,
        user_config_dir=USER_CONFIG_DIR,
    )

    return JSONResponse(
        {"rule": rule.model_dump(mode="json", by_alias=True)},
        status_code=201,
    )


async def delete_permission_rule(request: Request) -> JSONResponse:
    """Delete a normalized permission rule from its declared scope."""

    rule_id = str(request.path_params["rule_id"])
    destination = str(request.query_params.get("destination") or "").lower()
    chat_id = request.query_params.get("chat_id")
    if destination not in {"global", "session"}:
        return JSONResponse(
            {"error": "destination must be global or session"},
            status_code=400,
        )

    deleted = False
    if destination == "global":
        deleted = delete_global_permission_rule(
            PROJECT_DIR,
            logger,
            rule_id,
            user_config_dir=USER_CONFIG_DIR,
        )
        if deleted:
            CONFIG.permission_rules = [
                rule
                for rule in CONFIG.permission_rules
                if not isinstance(rule, dict) or rule.get("id") != rule_id
            ]
    else:
        if not chat_id:
            return JSONResponse(
                {"error": "chat_id is required for session rules"},
                status_code=400,
            )
        db = get_database()
        chat = db.get_chat(chat_id)
        if chat is None:
            return JSONResponse({"error": "Chat not found"}, status_code=404)
        rules = list((chat.config or {}).get("permission_rules") or [])
        filtered = [
            rule
            for rule in rules
            if not isinstance(rule, dict) or rule.get("id") != rule_id
        ]
        deleted = len(filtered) != len(rules)
        if deleted:
            db.merge_chat_config(chat_id, {"permission_rules": filtered})

    if not deleted:
        return JSONResponse({"error": "Permission rule not found"}, status_code=404)
    return JSONResponse({"deleted": True, "id": rule_id})
