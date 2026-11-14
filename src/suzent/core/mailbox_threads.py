"""Source adapters for the shared inbox thread and presentation contract."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel

from suzent.database.models import MailboxItemModel


_ACTIVITIES = {
    "opened": "created",
    "closed": "closed",
    "reopened": "reopened",
    "synchronize": "updated",
    "edited": "edited",
    "labeled": "label_added",
    "unlabeled": "label_removed",
    "assigned": "assigned",
    "unassigned": "unassigned",
    "ready_for_review": "review_ready",
    "converted_to_draft": "draft",
}


class MailboxPresentation(BaseModel):
    threadKey: str
    title: str
    source: str
    context: str | None = None
    icon: Literal["inbox", "code"] = "inbox"
    activity: str | None = None
    detail: str | None = None


def _object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError, RecursionError):
        return {}


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _payload(item: MailboxItemModel) -> dict[str, Any]:
    text = item.payload.strip()
    if text.startswith("<webhook_payload>\n") and text.endswith("\n</webhook_payload>"):
        text = text[len("<webhook_payload>\n") : -len("\n</webhook_payload>")]
        if not text.startswith("{"):
            text = text.partition("\n\n")[2]
    return _object(text)


def _key(*parts: str) -> str:
    # Opaque keys let scoped mobile clients group without exposing host routing metadata.
    value = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(value.encode()).hexdigest()


def _github(item: MailboxItemModel, body: dict[str, Any]) -> dict[str, Any]:
    kind, _, action = item.event_type.partition(".")
    if kind not in {"pull_request", "issues"}:
        return {}
    subject = body.get("pull_request" if kind == "pull_request" else "issue")
    subject = subject if isinstance(subject, dict) else {}
    repository = body.get("repository")
    repository = repository if isinstance(repository, dict) else {}
    repo = _text(repository.get("full_name"))
    number = subject.get("number") or body.get("number")
    title = _text(subject.get("title"))
    match = re.fullmatch(
        r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+) — #(\d+) (.+)", item.summary
    )
    known = _ACTIVITIES
    if match:
        repo = repo or match[1]
        number = number or int(match[2])
        if not title:
            title = match[3]
            suffix = f" ({action})"
            if action in known and title.endswith(suffix) and len(title) > len(suffix):
                title = title[: -len(suffix)]
    if (
        not repo
        or not isinstance(number, int)
        or isinstance(number, bool)
        or number <= 0
    ):
        return {}
    label = body.get("label")
    detail = (
        _text(label.get("name"))
        if isinstance(label, dict) and action in {"labeled", "unlabeled"}
        else None
    )
    return {
        "threadKey": _key("webhook", "github", kind, repo.casefold(), str(number)),
        "title": title or item.summary,
        "context": f"{repo} · #{number}",
        "source": "GitHub",
        "icon": "code",
        "activity": _ACTIVITIES.get(action),
        "detail": detail,
    }


def mailbox_presentation(item: MailboxItemModel) -> MailboxPresentation:
    """Resolve identity once on the server; clients only group by the returned key."""
    body = _payload(item)
    source = item.source_name
    key = (
        _key(item.source_kind, source, "signature", item.signature)
        if item.signature
        else _key("item", str(item.id))
    )
    result = MailboxPresentation(threadKey=key, title=item.summary, source=source)
    if item.source_kind == "agent_inbox":
        headers = _object(item.headers_json)
        sender = _text(headers.get("from")) or source or "system"
        sender = "subagent" if sender.startswith("subagent-") else sender
        participants = sorted([sender, item.target_chat_id or "unknown"])
        return result.model_copy(update={"threadKey": _key("agent", *participants)})
    if item.source_kind == "webhook":
        activity = _text(body.get("activity"))
        if activity in _ACTIVITIES.values():
            result = result.model_copy(
                update={"activity": activity, "detail": _text(body.get("detail"))}
            )
        # Any webhook can opt into subject threads without a client-specific adapter.
        thread_id = _text(body.get("thread_id"))
        if thread_id:
            return result.model_copy(
                update={
                    "threadKey": _key("webhook", source, "subject", thread_id),
                    "title": _text(body.get("subject")) or item.summary,
                    "context": _text(body.get("context")),
                }
            )
        if source.casefold() == "github":
            return result.model_copy(update=_github(item, body))
    return result
