"""REST API routes for the unified Mailbox (Agent Inbox + Webhooks + Dynamic Router)."""

from __future__ import annotations

import json
from sqlmodel import select
from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.core.focal_agent import FOCAL_CHAT_ID, FOCAL_TITLE
from suzent.core.mailbox import (
    MissingTargetError,
    target_exists,
    get_mailbox_webhook_path,
    list_routable_targets,
    resolve_target_label,
    rotate_mailbox_token,
    route_or_override_mailbox_item,
)
from suzent.core.webhooks import webhook_path
from suzent.database import (
    AgentInboxMessageModel,
    ChatDatabase,
    MailboxItemModel,
    MailboxRuleModel,
    get_database,
)


def _endpoint_urls(request: Request, path: str) -> dict[str, str]:
    urls = {"webhook_path": path}
    app = request.scope.get("app")
    relay = getattr(getattr(app, "state", None), "relay", None)
    if relay is not None and (relay_url := relay.webhook_url(path)):
        urls["webhook_relay_url"] = relay_url
    return urls


def _item_to_dict(item: MailboxItemModel) -> dict:
    try:
        headers = json.loads(item.headers_json or "{}")
    except ValueError:
        headers = {}
    return {
        "id": item.id,
        "source_kind": item.source_kind,
        "source_name": item.source_name,
        "event_type": item.event_type,
        "signature": item.signature,
        "summary": item.summary,
        "headers": headers,
        "payload": item.payload,
        "route_status": item.route_status,
        "target_chat_id": item.target_chat_id,
        "target_label": item.target_label,
        "rule_origin": item.rule_origin,
        "reason": item.reason,
        "inbox_message_id": item.inbox_message_id,
        "spooled_at": item.spooled_at,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _resolve_sender_name(
    db: ChatDatabase, msg: AgentInboxMessageModel, chat_labels: dict[str, str]
) -> str:
    payload = msg.payload or {}
    if payload.get("sender_label"):
        return str(payload["sender_label"])
    scid = msg.sender_chat_id or ""
    if not scid:
        return "system"
    if scid == FOCAL_CHAT_ID:
        return FOCAL_TITLE
    if scid == "system-dream-lint":
        return "dream-lint"
    if scid.startswith("subagent-"):
        return "subagent"
    if scid in chat_labels:
        return chat_labels[scid]
    lbl = resolve_target_label(db, scid)
    if lbl:
        chat_labels[scid] = lbl
        return lbl
    return scid[:12]


def _agent_inbox_to_dict(
    db: ChatDatabase,
    msg: AgentInboxMessageModel,
    synthetic_id: int,
    chat_labels: dict[str, str],
) -> dict:
    sender = _resolve_sender_name(db, msg, chat_labels)
    tcid = msg.target_chat_id
    if tcid not in chat_labels:
        chat_labels[tcid] = resolve_target_label(db, tcid) or tcid[:12]
    target_label = chat_labels[tcid]

    kind_map = {
        "agent_message": "mail",
        "remote_agent_message": "peer",
        "session_reply_notification": "reply",
        "session_finished_notification": "done",
        "subagent_result": "subagent",
    }
    short_kind = kind_map.get(msg.kind, msg.kind)
    raw = (msg.content or "").strip()
    lines = [
        ln.strip()
        for ln in raw.splitlines()
        if ln.strip() and not ln.strip().startswith("<!-- suzent-agent-inbox:")
    ]
    summary = lines[0][:240] if lines else f"{sender} → {target_label}"
    if msg.kind == "subagent_result":
        for ln in lines:
            if ln.lower().startswith("task:"):
                summary = ln[5:].strip()[:240]
                break

    return {
        "id": synthetic_id,
        "source_kind": "agent_inbox",
        "source_name": sender,
        "event_type": short_kind,
        "signature": f"inbox:{msg.kind}",
        "summary": summary,
        "headers": {
            "message_id": msg.message_id,
            "kind": msg.kind,
            "status": msg.status,
            "from": msg.sender_chat_id or "",
            "to": msg.target_chat_id,
        },
        "payload": raw,
        "route_status": "routed" if msg.status != "failed" else "error",
        "target_chat_id": tcid,
        "target_label": target_label,
        "rule_origin": "pinned",
        "reason": None,
        "inbox_message_id": msg.message_id,
        "spooled_at": None,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


def _rule_to_dict(rule: MailboxRuleModel) -> dict:
    return {
        "id": rule.id,
        "signature": rule.signature,
        "name": rule.name,
        "source_kind": rule.source_kind,
        "action": rule.action,
        "target_chat_id": rule.target_chat_id,
        "target_label": rule.target_label,
        "origin": rule.origin,
        "reason": rule.reason,
        "hit_count": rule.hit_count,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }


def _safe_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


async def list_mailbox_items_route(request: Request) -> JSONResponse:
    db = get_database()
    limit = min(200, max(1, _safe_int(request.query_params.get("limit"), 60)))
    offset = max(0, _safe_int(request.query_params.get("offset"), 0))
    route_status = request.query_params.get("route_status") or None
    source_kind = request.query_params.get("source_kind") or None

    mailbox_rows = db.list_mailbox_items(limit=200)
    linked_msg_ids = {r.inbox_message_id for r in mailbox_rows if r.inbox_message_id}

    combined: list[dict] = [_item_to_dict(r) for r in mailbox_rows]

    # Merge cross-session messages from the existing agent_inbox_messages bus
    try:
        with db._session() as session:
            stmt = (
                select(AgentInboxMessageModel)
                .where(AgentInboxMessageModel.kind != "background_task_result")
                .order_by(AgentInboxMessageModel.created_at.desc())
                .limit(100)
            )
            inbox_rows = list(session.exec(stmt).all())
        chat_labels: dict[str, str] = {FOCAL_CHAT_ID: FOCAL_TITLE}
        for idx, msg in enumerate(inbox_rows, start=1):
            if msg.message_id in linked_msg_ids:
                continue
            combined.append(_agent_inbox_to_dict(db, msg, -idx, chat_labels))
    except Exception:
        pass

    combined.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    routed_count = sum(1 for x in combined if x["route_status"] == "routed")
    unrouted_count = sum(1 for x in combined if x["route_status"] == "unrouted")

    filtered = combined
    if route_status == "routed":
        filtered = [x for x in filtered if x["route_status"] == "routed"]
    elif route_status == "unrouted":
        filtered = [x for x in filtered if x["route_status"] == "unrouted"]
    if source_kind:
        filtered = [x for x in filtered if x["source_kind"] == source_kind]

    return JSONResponse(
        {
            "items": filtered[offset : offset + limit],
            "counts": {
                "all": len(combined),
                "routed": routed_count,
                "unrouted": unrouted_count,
            },
            "targets": list_routable_targets(db),
            "endpoint": _endpoint_urls(request, get_mailbox_webhook_path()),
        }
    )


async def route_mailbox_item_route(request: Request) -> JSONResponse:
    item_id = int(request.path_params["item_id"])
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    action = str(data.get("action") or "route")
    target_chat_id = data.get("target_chat_id")
    pin_rule = bool(data.get("pin_rule", True))

    try:
        updated = route_or_override_mailbox_item(
            item_id,
            action=action,
            target_chat_id=target_chat_id,
            pin_rule=pin_rule,
        )
    except MissingTargetError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if updated is None:
        return JSONResponse({"error": "Mailbox item not found"}, status_code=404)
    return JSONResponse({"item": _item_to_dict(updated)})


async def delete_mailbox_item_route(request: Request) -> JSONResponse:
    item_id = int(request.path_params["item_id"])
    db = get_database()
    if item_id < 0:
        return JSONResponse({"deleted": True, "id": item_id})
    if not db.delete_mailbox_item(item_id):
        return JSONResponse({"error": "Mailbox item not found"}, status_code=404)
    return JSONResponse({"deleted": True, "id": item_id})


async def list_mailbox_rules_route(request: Request) -> JSONResponse:
    db = get_database()
    rules = db.list_mailbox_rules()
    return JSONResponse(
        {
            "rules": [_rule_to_dict(r) for r in rules],
            "targets": list_routable_targets(db),
        }
    )


async def update_mailbox_rule_route(request: Request) -> JSONResponse:
    rule_id = int(request.path_params["rule_id"])
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    db = get_database()
    action = str(data.get("action") or "route")
    target_chat_id = data.get("target_chat_id") if action == "route" else None
    if target_chat_id and not target_exists(db, target_chat_id):
        return JSONResponse(
            {"error": str(MissingTargetError(target_chat_id))}, status_code=400
        )
    target_label = resolve_target_label(db, target_chat_id) if target_chat_id else None
    reason = data.get("reason") or (
        f"Pinned by user: route to {target_label}."
        if action == "route"
        else "Pinned by user: do not route (store in Inbox only)."
    )

    updated = db.update_mailbox_rule(
        rule_id,
        action=action,
        target_chat_id=target_chat_id,
        target_label=target_label,
        origin="pinned",
        reason=reason,
    )
    if updated is None:
        return JSONResponse({"error": "Rule not found"}, status_code=404)
    return JSONResponse({"rule": _rule_to_dict(updated)})


async def delete_mailbox_rule_route(request: Request) -> JSONResponse:
    rule_id = int(request.path_params["rule_id"])
    db = get_database()
    if not db.delete_mailbox_rule(rule_id):
        return JSONResponse({"error": "Rule not found"}, status_code=404)
    return JSONResponse({"deleted": True, "id": rule_id})


async def get_mailbox_endpoint_route(request: Request) -> JSONResponse:
    return JSONResponse(_endpoint_urls(request, get_mailbox_webhook_path()))


async def rotate_mailbox_endpoint_route(request: Request) -> JSONResponse:
    token = rotate_mailbox_token()
    return JSONResponse(_endpoint_urls(request, webhook_path(token)))
