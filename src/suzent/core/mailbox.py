"""Unified Mailbox & Dynamic LLM-Crystallized Router for inbound events."""

from __future__ import annotations

import asyncio
import hmac
import json
import uuid
from typing import Any, Optional

from suzent.core.focal_agent import FOCAL_CHAT_ID, FOCAL_TITLE, get_or_create_focal_chat
from suzent.core.secrets import get_secret_manager
from suzent.core.webhooks import (
    build_webhook_section,
    format_webhook_payload,
    hash_webhook_token,
    new_webhook_token,
    webhook_path,
)
from suzent.database import (
    ChatDatabase,
    MailboxItemModel,
    MailboxRuleModel,
    get_database,
)
from suzent.logger import get_logger

logger = get_logger(__name__)

MAILBOX_TOKEN_SECRET = "SUZENT_MAILBOX::webhook_token"
MAILBOX_TOKEN_HASH_SECRET = "SUZENT_MAILBOX::webhook_token_hash"

_QUIET_GITHUB_EVENTS = frozenset(
    {
        "ping",
        "workflow_run.success",
        "workflow_run.skipped",
        "workflow_run.cancelled",
        "workflow_run.in_progress",
        "workflow_run.queued",
        "workflow_run.requested",
        "check_run.success",
        "check_run.neutral",
        "check_run.skipped",
        "check_suite.success",
        "status.success",
    }
)


def get_or_create_mailbox_token() -> str:
    """Return the universal Mailbox webhook token, minting one if needed."""
    sm = get_secret_manager()
    token = sm.get_backend_only(MAILBOX_TOKEN_SECRET)
    if not token:
        token, token_hash = new_webhook_token()
        sm.set_backend_only(MAILBOX_TOKEN_SECRET, token)
        sm.set_backend_only(MAILBOX_TOKEN_HASH_SECRET, token_hash)
    elif not sm.get_backend_only(MAILBOX_TOKEN_HASH_SECRET):
        sm.set_backend_only(MAILBOX_TOKEN_HASH_SECRET, hash_webhook_token(token))
    return token


def rotate_mailbox_token() -> str:
    """Mint and save a fresh universal Mailbox webhook token."""
    sm = get_secret_manager()
    token, token_hash = new_webhook_token()
    sm.set_backend_only(MAILBOX_TOKEN_SECRET, token)
    sm.set_backend_only(MAILBOX_TOKEN_HASH_SECRET, token_hash)
    return token


def is_mailbox_token(token: str) -> bool:
    """Check whether ``token`` matches the universal Mailbox webhook token."""
    if not token:
        return False
    sm = get_secret_manager()
    stored_hash = sm.get_backend_only(MAILBOX_TOKEN_HASH_SECRET)
    if not stored_hash:
        get_or_create_mailbox_token()
        stored_hash = sm.get_backend_only(MAILBOX_TOKEN_HASH_SECRET)
    return bool(
        stored_hash and hmac.compare_digest(hash_webhook_token(token), stored_hash)
    )


def get_mailbox_webhook_path() -> str:
    return webhook_path(get_or_create_mailbox_token())


def resolve_target_label(
    db: ChatDatabase, target_chat_id: Optional[str]
) -> Optional[str]:
    if not target_chat_id:
        return None
    if target_chat_id == FOCAL_CHAT_ID:
        return FOCAL_TITLE
    chat = db.get_chat(target_chat_id)
    if chat is not None:
        if chat.project_id and chat.project_id != "default":
            proj = db.get_project(chat.project_id)
            if proj:
                return f"{proj.name} · {chat.title}"
        return chat.title or target_chat_id
    return target_chat_id


def list_routable_targets(db: ChatDatabase) -> list[dict[str, str]]:
    """Return available routing targets (Regent first, then active project sessions)."""
    targets: list[dict[str, str]] = [
        {
            "chat_id": FOCAL_CHAT_ID,
            "label": f"{FOCAL_TITLE} (Focal Agent)",
            "kind": "regent",
        }
    ]
    seen = {FOCAL_CHAT_ID}
    try:
        projects = {p.id: p.name for p in db.list_projects(include_archived=False)}
        chats = db.list_chats(limit=40)
        for chat in chats:
            cid = getattr(chat, "id", None)
            if not cid or cid in seen or cid.startswith("subagent_"):
                continue
            title = getattr(chat, "title", None) or cid
            proj_id = getattr(chat, "project_id", None)
            proj_name = projects.get(proj_id, proj_id) if proj_id else None
            label = (
                f"[{proj_name}] {title}"
                if proj_name and proj_id != "default"
                else title
            )
            targets.append({"chat_id": cid, "label": label, "kind": "agent"})
            seen.add(cid)
    except Exception as exc:
        logger.debug("Could not list routable chats: {}", exc)
    return targets


def extract_event_metadata(
    *,
    source_kind: str = "webhook",
    body_bytes: bytes = b"",
    headers: Optional[dict[str, str]] = None,
    fallback_source: str = "webhook",
    fallback_event: str = "event",
    fallback_summary: str = "",
) -> dict[str, str]:
    """Extract canonical (source_name, event_type, signature, summary, rule_name) from an inbound event."""
    hdrs = {k.lower(): str(v) for k, v in (headers or {}).items()}
    raw_text = body_bytes.decode("utf-8", errors="replace").strip()
    data: dict[str, Any] = {}
    if raw_text.startswith("{"):
        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict):
                data = parsed
        except ValueError:
            pass

    # 1. GitHub Webhook
    if "x-github-event" in hdrs:
        gh_event = hdrs["x-github-event"].strip().lower()
        repo = str((data.get("repository") or {}).get("full_name") or "").strip()
        action = str(data.get("action") or "").strip().lower()

        if gh_event == "workflow_run":
            wf = data.get("workflow_run") or {}
            conclusion = str(wf.get("conclusion") or action or "running").lower()
            event_type = f"workflow_run.{conclusion}"
            wf_name = wf.get("name") or "CI"
            branch = wf.get("head_branch") or "main"
            summary = f"{repo or 'GitHub'} — CI '{wf_name}' {conclusion} on {branch}"
        elif gh_event == "check_run":
            cr = data.get("check_run") or {}
            conclusion = str(cr.get("conclusion") or action or "running").lower()
            event_type = f"check_run.{conclusion}"
            cr_name = cr.get("name") or "Check"
            summary = f"{repo or 'GitHub'} — Check '{cr_name}' {conclusion}"
        elif gh_event == "release":
            rel = data.get("release") or {}
            tag = rel.get("tag_name") or rel.get("name") or "new release"
            event_type = f"release.{action}" if action else "release"
            summary = f"{repo or 'GitHub'} — {tag} {action or 'released'}"
        elif gh_event == "ping":
            event_type = "ping"
            zen = data.get("zen") or "webhook configured"
            summary = f"Webhook ping from {repo or 'GitHub'} ({zen})"
        elif gh_event == "push":
            event_type = "push"
            ref = str(data.get("ref") or "").removeprefix("refs/heads/")
            commits = len(data.get("commits") or [])
            summary = (
                f"{repo or 'GitHub'} — {commits} commit(s) pushed to {ref or 'repo'}"
            )
        elif gh_event in ("issues", "pull_request"):
            item = data.get("issue") or data.get("pull_request") or {}
            num = item.get("number") or ""
            title = item.get("title") or gh_event
            event_type = f"{gh_event}.{action}" if action else gh_event
            summary = f"{repo or 'GitHub'} — #{num} {title} ({action or 'updated'})"
        else:
            event_type = f"{gh_event}.{action}" if action else gh_event
            summary = f"{repo or 'GitHub'} — {event_type}"

        if event_type in _QUIET_GITHUB_EVENTS:
            signature = f"github:{event_type}:*"
            rule_name = f"github · {event_type}"
        else:
            signature = f"github:{event_type}:{repo or '*'}"
            rule_name = f"github · {event_type}" + (f" ({repo})" if repo else "")

        return {
            "source_name": "github",
            "event_type": event_type,
            "signature": signature,
            "summary": summary[:240],
            "rule_name": rule_name,
        }

    # 2. Scheduled task or Peer or Email or Custom Webhook
    source_name = (
        str(data.get("source") or hdrs.get("x-event-source") or fallback_source)
        .strip()
        .lower()
        or "webhook"
    )
    event_type = (
        str(
            data.get("event")
            or data.get("type")
            or hdrs.get("x-event-type")
            or hdrs.get("x-gitlab-event")
            or fallback_event
        )
        .strip()
        .lower()
        or "event"
    )
    summary = (
        fallback_summary
        or str(
            data.get("summary")
            or data.get("title")
            or data.get("message")
            or data.get("subject")
            or data.get("content")
            or raw_text[:140]
            or f"{source_name} · {event_type}"
        ).strip()
    )
    summary = " ".join(summary.splitlines())[:240]
    signature = f"{source_name}:{event_type}"
    rule_name = f"{source_name} · {event_type}"
    return {
        "source_name": source_name,
        "event_type": event_type,
        "signature": signature,
        "summary": summary,
        "rule_name": rule_name,
    }


async def _llm_triage_first_seen(
    db: ChatDatabase,
    *,
    source_kind: str,
    source_name: str,
    event_type: str,
    signature: str,
    summary: str,
    payload_preview: str,
    preferred_chat_id: Optional[str] = None,
) -> tuple[str, Optional[str], str]:
    """Decide initial routing for a never-before-seen event signature.

    Returns ``(action, target_chat_id, reason)``.
    """
    if event_type == "ping":
        return (
            "none",
            None,
            "Webhook verification ping; stored in Mailbox without waking an agent.",
        )

    if preferred_chat_id:
        return (
            "route",
            preferred_chat_id,
            f"Bound to target session '{resolve_target_label(db, preferred_chat_id)}'.",
        )

    # Attempt fast LLM classification (bounded to 3.0s; safe fallback to Regent)
    try:
        import litellm
        from suzent.config import CONFIG

        model = getattr(CONFIG, "model", None)
        if model:
            targets = list_routable_targets(db)
            target_desc = "\n".join(
                f"- {t['chat_id']}: {t['label']}" for t in targets[:12]
            )
            prompt = (
                "You are Suzent's inbound Mailbox Router. A new event type arrived for the first time.\n"
                "Decide whether future events with this signature should:\n"
                "1) route to 'focal-suzent' (Regent, the default global orchestrator),\n"
                "2) route to a specific project session from the list below (only if the repo/subject clearly matches),\n"
                "3) 'none' (do not route / store in inbox only) if it is low-signal noise, a routine ping, or a passing status check.\n\n"
                f"Available targets:\n{target_desc}\n\n"
                f"Event signature: {signature}\n"
                f"Summary: {summary}\n"
                f"Payload preview: {payload_preview[:600]}\n\n"
                'Reply ONLY with compact JSON: {"action": "route"|"none", "target_chat_id": "focal-suzent"|"<chat_id>"|null, "reason": "<one short sentence>"}'
            )
            resp = await asyncio.wait_for(
                litellm.acompletion(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=120,
                ),
                timeout=3.0,
            )
            content = (
                resp.choices[0].message.content or ""
                if resp and getattr(resp, "choices", None)
                else ""
            ).strip()
            if "{" in content and "}" in content:
                raw_json = content[content.find("{") : content.rfind("}") + 1]
                parsed = json.loads(raw_json)
                act = str(parsed.get("action") or "route").lower()
                if act in ("route", "none"):
                    tgt = parsed.get("target_chat_id") if act == "route" else None
                    valid_ids = {t["chat_id"] for t in targets}
                    if act == "route" and (not tgt or tgt not in valid_ids):
                        tgt = FOCAL_CHAT_ID
                    reason = str(
                        parsed.get("reason")
                        or "Auto-classified on first arrival by LLM router."
                    )[:200]
                    return act, tgt, reason
    except Exception as exc:
        logger.debug("Mailbox LLM triage skipped/fell back to Regent: {}", exc)

    return (
        "route",
        FOCAL_CHAT_ID,
        "Default route: high-signal or novel inbound events go to Regent.",
    )


async def resolve_or_learn_rule(
    db: ChatDatabase,
    *,
    source_kind: str,
    source_name: str,
    event_type: str,
    signature: str,
    rule_name: str,
    summary: str,
    payload_preview: str,
    preferred_chat_id: Optional[str] = None,
) -> MailboxRuleModel:
    """Return the cached rule for ``signature``, or triage once and crystallize a new rule."""
    existing = db.get_mailbox_rule_by_signature(signature)
    if existing is None and ":" in signature:
        wildcard = f"{source_name}:{event_type}:*"
        if wildcard != signature:
            existing = db.get_mailbox_rule_by_signature(wildcard)

    if existing is not None:
        db.record_mailbox_rule_hit(existing.id)
        return existing

    action, target_chat_id, reason = await _llm_triage_first_seen(
        db,
        source_kind=source_kind,
        source_name=source_name,
        event_type=event_type,
        signature=signature,
        summary=summary,
        payload_preview=payload_preview,
        preferred_chat_id=preferred_chat_id,
    )
    target_label = (
        resolve_target_label(db, target_chat_id) if action == "route" else None
    )
    return db.upsert_mailbox_rule(
        signature=signature,
        name=rule_name,
        source_kind=source_kind,
        action=action,
        target_chat_id=target_chat_id,
        target_label=target_label,
        origin="learned",
        reason=reason,
        increment_hit=True,
    )


def _deliver_item_to_agent(
    db: ChatDatabase,
    item: MailboxItemModel,
    target_chat_id: str,
    custom_prompt: Optional[str] = None,
) -> str:
    """Queue a Mailbox item into ``agent_inbox`` for ``target_chat_id`` and return ``message_id``."""
    from suzent.core.agent_inbox import enqueue_agent_message

    if target_chat_id == FOCAL_CHAT_ID:
        get_or_create_focal_chat()
    elif db.get_chat(target_chat_id) is None:
        # Ensure cron-* or named chat exists before queueing into agent_inbox
        db.ensure_channel_chat(
            target_chat_id,
            title=item.target_label or f"Mailbox · {item.source_name}",
            platform="mailbox",
        )

    msg_id = f"mailbox_{item.id}_{uuid.uuid4().hex[:10]}"
    header_line = f"[Mailbox Event #{item.id} · {item.source_name} · {item.event_type}]"
    if custom_prompt:
        content = f"{header_line}\n{custom_prompt.strip()}{build_webhook_section(item.payload)}"
    else:
        content = (
            f"{header_line}\n"
            f"Summary: {item.summary}"
            f"{build_webhook_section(item.payload)}"
        )

    enqueue_agent_message(
        message_id=msg_id,
        sender_chat_id=None,
        target_chat_id=target_chat_id,
        content=content[:19500],
        kind="remote_agent_message",
        payload={
            "mailbox_item_id": item.id,
            "sender_label": f"Mailbox ({item.source_name})",
            "sender_agent_id": f"mailbox:{item.id}",
        },
    )
    return msg_id


async def ingest_mailbox_event(
    *,
    source_kind: str = "webhook",
    body_bytes: bytes = b"",
    headers: Optional[dict[str, str]] = None,
    fallback_source: str = "webhook",
    fallback_event: str = "event",
    fallback_summary: str = "",
    preferred_chat_id: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    dispatch: bool = True,
) -> MailboxItemModel:
    """Store an inbound event in the Mailbox, evaluate/learn its routing rule, and dispatch if routed."""
    db = get_database()
    hdrs = {k.lower(): str(v) for k, v in (headers or {}).items()}
    meta = extract_event_metadata(
        source_kind=source_kind,
        body_bytes=body_bytes,
        headers=hdrs,
        fallback_source=fallback_source,
        fallback_event=fallback_event,
        fallback_summary=fallback_summary,
    )
    formatted_payload = format_webhook_payload(body_bytes, hdrs)
    safe_headers = {
        k: v
        for k, v in hdrs.items()
        if not any(
            secret in k
            for secret in ("authorization", "token", "secret", "signature", "cookie")
        )
    }
    spooled_at = hdrs.get("x-suzent-relay-queued-at")

    if not dispatch and preferred_chat_id:
        action = "route"
        target_chat_id = preferred_chat_id
        target_label = resolve_target_label(db, target_chat_id)
        route_status = "routed"
        rule_origin = "pinned"
        reason = f"Delivered to bound webhook task '{fallback_source}'."
    else:
        rule = await resolve_or_learn_rule(
            db,
            source_kind=source_kind,
            source_name=meta["source_name"],
            event_type=meta["event_type"],
            signature=meta["signature"],
            rule_name=meta["rule_name"],
            summary=meta["summary"],
            payload_preview=formatted_payload,
            preferred_chat_id=preferred_chat_id,
        )
        action = rule.action
        target_chat_id = rule.target_chat_id if action == "route" else None
        target_label = (
            resolve_target_label(db, target_chat_id) if target_chat_id else None
        )
        route_status = (
            "routed" if (action == "route" and target_chat_id) else "unrouted"
        )
        rule_origin = rule.origin
        reason = rule.reason

    item = db.create_mailbox_item(
        source_kind=source_kind,
        source_name=meta["source_name"],
        event_type=meta["event_type"],
        signature=meta["signature"],
        summary=meta["summary"],
        headers_json=json.dumps(safe_headers, ensure_ascii=False),
        payload=formatted_payload,
        route_status=route_status,
        target_chat_id=target_chat_id,
        target_label=target_label,
        rule_origin=rule_origin,
        reason=reason,
        spooled_at=spooled_at,
    )

    if dispatch and route_status == "routed" and target_chat_id:
        try:
            msg_id = _deliver_item_to_agent(
                db, item, target_chat_id, custom_prompt=custom_prompt
            )
            item = db.update_mailbox_item(item.id, inbox_message_id=msg_id) or item
        except Exception as exc:
            logger.error("Failed to dispatch Mailbox item {}: {}", item.id, exc)
            item = (
                db.update_mailbox_item(
                    item.id, route_status="error", reason=f"Dispatch error: {exc}"
                )
                or item
            )

    return item


def route_or_override_mailbox_item(
    item_id: int,
    *,
    action: str,
    target_chat_id: Optional[str] = None,
    pin_rule: bool = True,
) -> Optional[MailboxItemModel]:
    """Manually route/replay a Mailbox item (and optionally pin the rule for its signature)."""
    db = get_database()
    item = db.get_mailbox_item(item_id)
    if item is None:
        return None

    if action == "none" or not target_chat_id:
        action = "none"
        target_chat_id = None
        target_label = None
        route_status = "unrouted"
    else:
        action = "route"
        target_label = resolve_target_label(db, target_chat_id)
        route_status = "routed"

    reason = (
        f"Pinned by user: route to {target_label}."
        if action == "route"
        else "Pinned by user: do not route (store in Inbox only)."
    )

    if pin_rule:
        db.upsert_mailbox_rule(
            signature=item.signature,
            name=f"{item.source_name} · {item.event_type}",
            source_kind=item.source_kind,
            action=action,
            target_chat_id=target_chat_id,
            target_label=target_label,
            origin="pinned",
            reason=reason,
            increment_hit=False,
        )

    inbox_msg_id = item.inbox_message_id
    if route_status == "routed" and target_chat_id:
        inbox_msg_id = _deliver_item_to_agent(db, item, target_chat_id)

    return db.update_mailbox_item(
        item.id,
        route_status=route_status,
        target_chat_id=target_chat_id,
        target_label=target_label,
        rule_origin="pinned" if pin_rule else "manual",
        reason=reason,
        inbox_message_id=inbox_msg_id,
    )
