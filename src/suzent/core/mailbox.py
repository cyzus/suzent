"""Unified Mailbox & Dynamic LLM-Crystallized Router for inbound events."""

from __future__ import annotations

import asyncio
import hmac
import json
import traceback
import uuid
from dataclasses import dataclass, field
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

_triage_locks: dict[str, asyncio.Lock] = {}
# Triage runs inside the webhook request; GitHub gives up after 10 seconds.
_TRIAGE_TIMEOUT_SECONDS = 8.0


async def _ask_router(prompt: str) -> str:
    """Ask the decision model to classify a new kind of event."""
    from suzent.core.role_router import ModelRole, get_role_router
    from suzent.llm import LLMClient

    model = get_role_router().get_model_id(ModelRole.DECISION)
    if not model:
        raise RuntimeError("no decision model configured")
    return await LLMClient(model=model).complete(
        prompt=prompt, temperature=0.0, max_tokens=120, reasoning_effort="none"
    )


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
) -> tuple[str, Optional[str], str, bool]:
    """Decide initial routing for a never-before-seen event signature.

    Returns ``(action, target_chat_id, reason, durable)``. ``durable`` is False
    for the Regent fallback used when the LLM could not decide (no model, a
    timeout, an error or an unreadable reply), so that guess is not saved as a
    rule and the next event of this kind is triaged again.
    """
    if event_type == "ping":
        return (
            "none",
            None,
            "Webhook verification ping; stored in Mailbox without waking an agent.",
            True,
        )

    try:
        targets = list_routable_targets(db)
        target_desc = "\n".join(f"- {t['chat_id']}: {t['label']}" for t in targets[:12])
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
        content = (
            await asyncio.wait_for(_ask_router(prompt), timeout=_TRIAGE_TIMEOUT_SECONDS)
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
                return act, tgt, reason, True
    except Exception as exc:
        logger.warning("Mailbox LLM triage failed, sending to Regent: {}", exc)

    return (
        "route",
        FOCAL_CHAT_ID,
        "Sent to Regent: the router could not classify this event yet.",
        False,
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
) -> MailboxRuleModel:
    """Return the cached rule for ``signature``, or triage once and crystallize a new rule."""
    # Events of one new kind often arrive together (a CI run's checks); triage
    # it once and let the others read the rule that run saves.
    async with _triage_locks.setdefault(signature, asyncio.Lock()):
        return await _resolve_or_learn_rule_locked(
            db,
            source_kind=source_kind,
            source_name=source_name,
            event_type=event_type,
            signature=signature,
            rule_name=rule_name,
            summary=summary,
            payload_preview=payload_preview,
        )


async def _resolve_or_learn_rule_locked(
    db: ChatDatabase,
    *,
    source_kind: str,
    source_name: str,
    event_type: str,
    signature: str,
    rule_name: str,
    summary: str,
    payload_preview: str,
) -> MailboxRuleModel:
    existing = db.get_mailbox_rule_by_signature(signature)
    if existing is None and ":" in signature:
        wildcard = f"{source_name}:{event_type}:*"
        if wildcard != signature:
            existing = db.get_mailbox_rule_by_signature(wildcard)

    if existing is not None:
        db.record_mailbox_rule_hit(existing.id)
        return existing

    action, target_chat_id, reason, durable = await _llm_triage_first_seen(
        db,
        source_kind=source_kind,
        source_name=source_name,
        event_type=event_type,
        signature=signature,
        summary=summary,
        payload_preview=payload_preview,
    )
    target_label = (
        resolve_target_label(db, target_chat_id) if action == "route" else None
    )
    if not durable:
        return MailboxRuleModel(
            signature=signature,
            name=rule_name,
            source_kind=source_kind,
            action=action,
            target_chat_id=target_chat_id,
            target_label=target_label,
            origin="default",
            reason=reason,
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


def target_exists(db: ChatDatabase, chat_id: str) -> bool:
    """Regent always exists (it is created on demand); other sessions must."""
    return chat_id == FOCAL_CHAT_ID or db.get_chat(chat_id) is not None


class MissingTargetError(LookupError):
    """A route points at a session that no longer exists."""

    def __init__(self, chat_id: str):
        super().__init__(f"Session '{chat_id}' no longer exists")
        self.chat_id = chat_id


def _deliver_item_to_agent(
    db: ChatDatabase,
    item: MailboxItemModel,
    target_chat_id: str,
    custom_prompt: Optional[str] = None,
) -> str:
    """Queue a Mailbox item into ``agent_inbox`` for ``target_chat_id`` and return ``message_id``."""
    from suzent.core.agent_inbox import enqueue_agent_message

    if not target_exists(db, target_chat_id):
        raise MissingTargetError(target_chat_id)
    if target_chat_id == FOCAL_CHAT_ID:
        get_or_create_focal_chat()

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


@dataclass(frozen=True)
class InboundEnvelope:
    """One inbound event, whatever its source, as the Mailbox stores it."""

    source_kind: str
    source_name: str
    event_type: str
    signature: str
    summary: str
    rule_name: str = ""
    payload: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    spooled_at: Optional[str] = None


def record_inbound(
    envelope: InboundEnvelope,
    *,
    target_chat_id: Optional[str],
    reason: str,
    inbox_message_id: Optional[str] = None,
) -> MailboxItemModel:
    """Store an event whose source already chose where it goes.

    Nothing is routed or delivered here: schedules, peer devices, agent
    messages and task webhooks deliver through their own paths and only need
    to appear in the Mailbox.
    """
    db = get_database()
    return db.create_mailbox_item(
        source_kind=envelope.source_kind,
        source_name=envelope.source_name,
        event_type=envelope.event_type,
        signature=envelope.signature,
        summary=envelope.summary,
        headers_json=json.dumps(envelope.headers, ensure_ascii=False),
        payload=envelope.payload,
        route_status="routed" if target_chat_id else "unrouted",
        target_chat_id=target_chat_id,
        target_label=resolve_target_label(db, target_chat_id),
        rule_origin="pinned",
        reason=reason,
        inbox_message_id=inbox_message_id,
        spooled_at=envelope.spooled_at,
    )


async def route_inbound(
    envelope: InboundEnvelope, *, custom_prompt: Optional[str] = None
) -> MailboxItemModel:
    """Store an event, let the rules (or the router) choose its target, and deliver it."""
    db = get_database()
    rule = await resolve_or_learn_rule(
        db,
        source_kind=envelope.source_kind,
        source_name=envelope.source_name,
        event_type=envelope.event_type,
        signature=envelope.signature,
        rule_name=envelope.rule_name
        or f"{envelope.source_name} · {envelope.event_type}",
        summary=envelope.summary,
        payload_preview=envelope.payload,
    )
    target_chat_id = rule.target_chat_id if rule.action == "route" else None
    item = db.create_mailbox_item(
        source_kind=envelope.source_kind,
        source_name=envelope.source_name,
        event_type=envelope.event_type,
        signature=envelope.signature,
        summary=envelope.summary,
        headers_json=json.dumps(envelope.headers, ensure_ascii=False),
        payload=envelope.payload,
        route_status="routed" if target_chat_id else "unrouted",
        target_chat_id=target_chat_id,
        target_label=resolve_target_label(db, target_chat_id),
        rule_origin=rule.origin,
        reason=rule.reason,
        spooled_at=envelope.spooled_at,
    )
    if target_chat_id:
        item = _dispatch(db, item, target_chat_id, custom_prompt)
    return item


def _dispatch(
    db: ChatDatabase,
    item: MailboxItemModel,
    target_chat_id: str,
    custom_prompt: Optional[str],
) -> MailboxItemModel:
    try:
        try:
            msg_id = _deliver_item_to_agent(
                db, item, target_chat_id, custom_prompt=custom_prompt
            )
        except MissingTargetError as missing:
            item = _reroute_to_regent(db, item, missing)
            msg_id = _deliver_item_to_agent(
                db, item, FOCAL_CHAT_ID, custom_prompt=custom_prompt
            )
        return db.update_mailbox_item(item.id, inbox_message_id=msg_id) or item
    except Exception as exc:
        logger.error(
            "Failed to dispatch Mailbox item {}: {}\n{}",
            item.id,
            exc,
            traceback.format_exc(),
        )
        return (
            db.update_mailbox_item(
                item.id, route_status="error", reason=f"Dispatch error: {exc}"
            )
            or item
        )


def webhook_envelope(
    body_bytes: bytes,
    headers: dict[str, str],
    *,
    fallback_source: str = "webhook",
) -> InboundEnvelope:
    """Describe an HTTP webhook delivery as an envelope."""
    hdrs = {k.lower(): str(v) for k, v in headers.items()}
    meta = extract_event_metadata(
        body_bytes=body_bytes, headers=hdrs, fallback_source=fallback_source
    )
    return InboundEnvelope(
        source_kind="webhook",
        source_name=meta["source_name"],
        event_type=meta["event_type"],
        signature=meta["signature"],
        summary=meta["summary"],
        rule_name=meta["rule_name"],
        payload=format_webhook_payload(body_bytes, hdrs),
        headers={
            k: v
            for k, v in hdrs.items()
            if not any(
                secret in k
                for secret in (
                    "authorization",
                    "token",
                    "secret",
                    "signature",
                    "cookie",
                )
            )
        },
        spooled_at=hdrs.get("x-suzent-relay-queued-at"),
    )


# Agent inbox kinds the Mailbox shows, with the short label it shows them under.
_INBOX_EVENT_TYPES = {
    "agent_message": "mail",
    "remote_agent_message": "peer",
    "session_reply_notification": "reply",
    "session_finished_notification": "done",
    "subagent_result": "subagent",
}
_INBOX_MARKER_PREFIX = "<!-- suzent-agent-inbox:"


def record_agent_message(message: dict[str, Any]) -> Optional[MailboxItemModel]:
    """Record one agent inbox message in the Mailbox as it is sent.

    Messages the Mailbox delivered itself already have their item, and
    background command results are internal bookkeeping, so neither is
    recorded again.
    """
    payload = message.get("payload") or {}
    kind = str(message.get("kind") or "")
    if payload.get("mailbox_item_id") is not None or kind == "background_task_result":
        return None

    db = get_database()
    sender_chat_id = message.get("sender_chat_id") or ""
    sender_agent_id = str(payload.get("sender_agent_id") or "")
    lines = [
        line.strip()
        for line in str(message.get("content") or "").splitlines()
        if line.strip() and not line.strip().startswith(_INBOX_MARKER_PREFIX)
    ]
    summary = lines[0] if lines else ""
    if kind == "subagent_result":
        summary = next(
            (line[5:].strip() for line in lines if line.lower().startswith("task:")),
            summary,
        )

    if sender_agent_id.startswith("device:"):
        source_kind, signature = "peer", f"peer:{sender_agent_id[7:]}"
    else:
        source_kind, signature = "agent_inbox", f"inbox:{kind}"
    sender = _sender_label(db, sender_chat_id, payload)
    envelope = InboundEnvelope(
        source_kind=source_kind,
        source_name=sender,
        event_type=_INBOX_EVENT_TYPES.get(kind, kind),
        signature=signature,
        summary=(summary or f"{sender} → {message.get('target_chat_id')}")[:240],
        payload="\n".join(lines),
        headers={
            "message_id": str(message.get("message_id") or ""),
            "kind": kind,
            "from": sender_chat_id,
            "to": str(message.get("target_chat_id") or ""),
        },
    )
    return record_inbound(
        envelope,
        target_chat_id=message.get("target_chat_id"),
        reason=f"Sent by {sender}.",
        inbox_message_id=message.get("message_id"),
    )


def _sender_label(db: ChatDatabase, sender_chat_id: str, payload: dict) -> str:
    if payload.get("sender_label"):
        return str(payload["sender_label"])
    if not sender_chat_id:
        return "system"
    if sender_chat_id == "system-dream-lint":
        return "dream-lint"
    if sender_chat_id.startswith("subagent-"):
        return "subagent"
    return resolve_target_label(db, sender_chat_id) or sender_chat_id[:12]


def _reroute_to_regent(
    db: ChatDatabase, item: MailboxItemModel, missing: MissingTargetError
) -> MailboxItemModel:
    """Send an item whose target session is gone to Regent instead.

    A learned rule is forgotten so the next event is triaged against the
    sessions that exist now; a pinned rule is the user's and stays until they
    change it.
    """
    rule = db.get_mailbox_rule_by_signature(item.signature)
    if rule is not None and rule.origin == "learned":
        db.delete_mailbox_rule(rule.id)
    logger.warning(
        "Mailbox item {} targeted missing session {}; sent to Regent",
        item.id,
        missing.chat_id,
    )
    return (
        db.update_mailbox_item(
            item.id,
            target_chat_id=FOCAL_CHAT_ID,
            target_label=FOCAL_TITLE,
            reason=f"{missing}; sent to Regent instead.",
        )
        or item
    )


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
        if not target_exists(db, target_chat_id):
            raise MissingTargetError(target_chat_id)
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
