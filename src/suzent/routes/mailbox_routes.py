"""REST API routes for the unified Mailbox and its dynamic router."""

from __future__ import annotations

import json

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.core.mailbox import (
    DEST_NONE,
    Destination,
    MissingTargetError,
    routing_fields,
    get_mailbox_webhook_path,
    list_destinations,
    rotate_mailbox_token,
    route_or_override_mailbox_item,
)
from suzent.core.webhooks import webhook_path
from suzent.database import MailboxItemModel, MailboxRuleModel, get_database


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
        "read_at": item.read_at.isoformat() if item.read_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _rule_to_dict(rule: MailboxRuleModel) -> dict:
    return {
        "id": rule.id,
        "signature": rule.signature,
        "name": rule.name,
        "source_kind": rule.source_kind,
        "destination": Destination.of_rule(rule).value,
        "target_label": rule.target_label,
        "cadence": rule.delivery,
        "digest_minutes": rule.digest_minutes,
        "prompt": rule.prompt,
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
    rows = db.list_mailbox_items(
        limit=limit,
        offset=offset,
        route_status=request.query_params.get("route_status") or None,
        source_kind=request.query_params.get("source_kind") or None,
    )
    # Delivery happens after the item is stored, so read its current status.
    statuses = db.agent_message_statuses(
        [row.inbox_message_id for row in rows if row.inbox_message_id]
    )
    items = []
    for row in rows:
        item = _item_to_dict(row)
        status = statuses.get(row.inbox_message_id or "")
        if status:
            item["headers"]["status"] = status
            if status == "failed":
                item["route_status"] = "error"
        items.append(item)

    counts = db.count_mailbox_items()
    return JSONResponse(
        {
            "items": items,
            "counts": {
                "all": sum(counts.values()),
                "routed": counts.get("routed", 0),
                "unrouted": counts.get("unrouted", 0),
                "unread": db.count_unread_mailbox_notifications(),
            },
            "destinations": list_destinations(db),
            "endpoint": _endpoint_urls(request, get_mailbox_webhook_path()),
        }
    )


async def mailbox_unread_route(request: Request) -> JSONResponse:
    return JSONResponse({"unread": get_database().count_unread_mailbox_notifications()})


async def mark_mailbox_read_route(request: Request) -> JSONResponse:
    """Mark notifications read: the given ``ids``, or every unread one."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    ids = data.get("ids") if isinstance(data, dict) else None
    if ids is not None and not (
        isinstance(ids, list) and all(isinstance(i, int) for i in ids)
    ):
        return JSONResponse(
            {"error": "ids must be a list of item ids"}, status_code=400
        )
    db = get_database()
    marked = db.mark_mailbox_notifications_read(ids)
    return JSONResponse(
        {"marked": marked, "unread": db.count_unread_mailbox_notifications()}
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
    if not db.delete_mailbox_item(item_id):
        return JSONResponse({"error": "Mailbox item not found"}, status_code=404)
    return JSONResponse({"deleted": True, "id": item_id})


async def list_mailbox_rules_route(request: Request) -> JSONResponse:
    db = get_database()
    rules = db.list_mailbox_rules()
    return JSONResponse(
        {
            "rules": [_rule_to_dict(r) for r in rules],
            "destinations": list_destinations(db),
        }
    )


async def update_mailbox_rule_route(request: Request) -> JSONResponse:
    rule_id = int(request.path_params["rule_id"])
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    db = get_database()
    destination = Destination.parse(data.get("destination"))
    if destination.missing(db):
        return JSONResponse(
            {"error": str(MissingTargetError(destination.value))}, status_code=400
        )
    cadence = str(data.get("cadence") or "now")
    if cadence not in ("now", "digest"):
        return JSONResponse({"error": f"Unknown cadence '{cadence}'"}, status_code=400)
    label = destination.label(db)
    updated = db.update_mailbox_rule(
        rule_id,
        delivery=cadence,
        digest_minutes=_safe_int(str(data.get("digest_minutes", 60)), 60),
        prompt=data.get("prompt") if destination.reaches_agent else None,
        origin="pinned",
        reason=data.get("reason")
        or (
            f"Pinned by user: send to {label}."
            if destination.kind != DEST_NONE
            else "Pinned by user: keep in the Mailbox only."
        ),
        **routing_fields(db, destination),
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
