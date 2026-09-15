"""Resource-scoped access to the desktop's existing tool approval queues."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import ConfigDict, Field
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.mobile.client_api import ChatRequest, authorize, forwarded, parse
from suzent.routes.mobile_routes import reply


class ApprovalChoice(ChatRequest):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=200)
    action_id: str = Field(min_length=1, max_length=200)
    kind: Literal["tool", "acp"] = "tool"


class ApprovalBatch(ChatRequest):
    decisions: list[ApprovalChoice] = Field(min_length=1, max_length=64)


def once_actions(decision: dict) -> list[dict]:
    return [
        {"id": action["id"], "behavior": action["behavior"]}
        for action in decision.get("actions", [])
        if isinstance(action, dict)
        and action.get("id")
        and action.get("behavior") in {"allow", "deny"}
        and action.get("scope", "once") == "once"
        and not action.get("permissionUpdates")
    ]


async def pending_approvals(request: Request, chat_id: str) -> list[dict]:
    from suzent.acp.permissions import get_permission_broker
    from suzent.routes.permission_routes import get_chat_permission_state

    scope = dict(request.scope)
    scope["path_params"] = {"chat_id": chat_id}
    response = await get_chat_permission_state(Request(scope, request.receive))
    if response.status_code != 200:
        raise HTTPException(response.status_code, "Conversation unavailable")
    result = []
    for item in json.loads(response.body)["pendingApprovals"]:
        actions = once_actions(item.get("decision") or {})
        if not item.get("approvalId") or not item.get("toolCallId"):
            continue
        result.append(
            {
                "id": item["approvalId"],
                "kind": "tool",
                "tool_call_id": item["toolCallId"],
                "tool_name": item.get("toolName") or "Tool",
                "args": json.dumps(item.get("args") or {}, ensure_ascii=False),
                "reason": (item.get("decision") or {}).get("reason") or "",
                "actions": actions,
            }
        )
    for item in get_permission_broker().list_pending(chat_id):
        tool = item.get("toolCall") or {}
        actions = [
            {
                "id": option.get("optionId") or option.get("id"),
                "behavior": "allow" if option["kind"] == "allow_once" else "deny",
            }
            for option in item.get("options", [])
            if option.get("kind") in {"allow_once", "reject_once"}
            and (option.get("optionId") or option.get("id"))
        ]
        if not any(action["behavior"] == "deny" for action in actions):
            actions.append({"id": "__suzent_cancel__", "behavior": "deny"})
        result.append(
            {
                "id": item["requestId"],
                "kind": "acp",
                "tool_call_id": tool.get("toolCallId") or item["requestId"],
                "tool_name": tool.get("title") or tool.get("kind") or "Tool",
                "args": json.dumps(
                    tool.get("rawInput") or tool.get("content") or {},
                    ensure_ascii=False,
                ),
                "reason": "",
                "actions": actions,
            }
        )
    return result


async def listing(request: Request) -> JSONResponse:
    chat_id = request.path_params["chat_id"]
    authorize(request, chat_id)
    pending = await pending_approvals(request, chat_id)
    authorize(request, chat_id)
    from suzent.core.stream_registry import is_background_streaming

    return reply({"pending": pending, "isRunning": is_background_streaming(chat_id)})


async def decide(request: Request) -> JSONResponse:
    body = await parse(request, ApprovalBatch)
    authorize(request, body.chat_id, "approve_tools")
    if any(choice.chat_id != body.chat_id for choice in body.decisions):
        raise HTTPException(400, "Mismatched conversation")
    pending = await pending_approvals(request, body.chat_id)
    authorize(request, body.chat_id, "approve_tools")
    by_id = {(item["kind"], item["id"]): item for item in pending}
    keys = [(choice.kind, choice.request_id) for choice in body.decisions]
    if len(set(keys)) != len(keys) or set(keys) != set(by_id):
        raise HTTPException(409, "Approvals changed; refresh before deciding")
    resolved = []
    for choice in body.decisions:
        item = by_id[(choice.kind, choice.request_id)]
        action = next(
            (action for action in item["actions"] if action["id"] == choice.action_id),
            None,
        )
        if action is None:
            raise HTTPException(403, "Approval action not offered to mobile clients")
        resolved.append((choice, item, action))
    if {choice.kind for choice, _, _ in resolved} == {"acp"}:
        from suzent.acp.permissions import get_permission_broker

        broker = get_permission_broker()
        # No awaits between validation and resolution: one event-loop turn wins.
        if any(
            not (entry := broker.get(choice.request_id))
            or entry.chat_id != body.chat_id
            or entry.future.done()
            for choice, _, _ in resolved
        ):
            raise HTTPException(409, "Approvals already resolved")
        for choice, _, action in resolved:
            broker.resolve(
                choice.request_id,
                approved=action["behavior"] == "allow",
                option_id=choice.action_id,
            )
        return reply({"ok": True})
    if any(choice.kind != "tool" for choice, _, _ in resolved):
        raise HTTPException(409, "Approval runtime changed")
    from suzent.database import get_database
    from suzent.routes.chat_routes import chat_send

    chat = get_database().get_chat(body.chat_id)
    stored = (
        {
            item.get("approvalId"): item
            for item in (chat.config or {}).get("_pending_approvals", [])
            if isinstance(item, dict)
        }
        if chat
        else {}
    )
    approvals = []
    for choice, item, action in resolved:
        record = stored.get(choice.request_id)
        if record is None:
            raise HTTPException(409, "Approvals already resolved")
        approvals.append(
            {
                "request_id": choice.request_id,
                "tool_call_id": item["tool_call_id"],
                "approved": action["behavior"] == "allow",
                "remember": "",
                "tool_name": item["tool_name"],
                **(
                    {"action_id": choice.action_id}
                    if isinstance(record.get("decision"), dict)
                    and record["decision"].get("actions")
                    else {}
                ),
            }
        )
    return await chat_send(
        forwarded(
            request,
            {"chat_id": body.chat_id, "message": "", "resume_approvals": approvals},
        )
    )
