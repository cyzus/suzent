"""Mailbox operations, each one himalaya run (or two) against one account."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from email.message import EmailMessage

from suzent.logger import get_logger

from . import himalaya
from .accounts import MailAccount
from .himalaya import MailError
from .message import MessageDetail, parse

logger = get_logger(__name__)

MAX_MESSAGE_BYTES = 30 * 1024 * 1024

# himalaya reports special-use roles for JMAP, Gmail and Graph but only the
# inbox for IMAP, so the usual folder names stand in for the rest.
_FALLBACK_NAMES = {
    "drafts": ("drafts", "draft", "草稿箱", "草稿", "[gmail]/drafts"),
    "sent": (
        "sent",
        "sent messages",
        "sent items",
        "sent mail",
        "已发送",
        "[gmail]/sent mail",
    ),
}


@dataclass
class SearchCriteria:
    query: str | None = None
    sender: str | None = None
    subject: str | None = None
    since: date | None = None
    unread_only: bool = False


@dataclass
class MessageSummary:
    id: str
    date: str
    sender: str
    subject: str
    unread: bool


def _quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_query(criteria: SearchCriteria) -> str:
    """The criteria in himalaya's query language, newest first."""
    clauses = []
    if criteria.query:
        term = _quoted(criteria.query)
        clauses.append(f"(subject {term} or from {term} or body {term})")
    if criteria.sender:
        clauses.append(f"from {_quoted(criteria.sender)}")
    if criteria.subject:
        clauses.append(f"subject {_quoted(criteria.subject)}")
    if criteria.since:
        # himalaya's `after` excludes the day itself.
        clauses.append(f"after {(criteria.since - timedelta(days=1)).isoformat()}")
    if criteria.unread_only:
        clauses.append("not flag seen")
    where = " and ".join(clauses)
    return f"{where} order by date desc".strip()


def _sender(envelope: dict) -> str:
    senders = envelope.get("from") or []
    if not senders:
        return ""
    first = senders[0]
    name, email = first.get("name"), first.get("email", "")
    return f"{name} <{email}>" if name else email


async def list_mailboxes(account: MailAccount, password: str) -> list[dict]:
    data = await himalaya.run(account, password, ["mailbox", "list"])
    return list((data or {}).get("mailboxes") or [])


async def special_mailbox(account: MailAccount, password: str, role: str) -> str | None:
    mailboxes = await list_mailboxes(account, password)
    for mailbox in mailboxes:
        if mailbox.get("role") == role:
            return mailbox["id"]
    names = _FALLBACK_NAMES[role]
    for mailbox in mailboxes:
        if str(mailbox.get("name", "")).lower() in names:
            return mailbox["id"]
    return None


async def search(
    account: MailAccount,
    password: str,
    folder: str,
    criteria: SearchCriteria,
    limit: int,
    page: int = 1,
) -> list[MessageSummary]:
    data = await himalaya.run(
        account,
        password,
        [
            "envelope",
            "search",
            f"--mailbox={folder}",
            f"--page-size={limit}",
            f"--page={page}",
            "--",
            build_query(criteria),
        ],
    )
    return [
        MessageSummary(
            id=str(envelope["id"]),
            date=str(envelope.get("date") or ""),
            sender=_sender(envelope),
            subject=str(envelope.get("subject") or ""),
            unread="seen" not in (envelope.get("flags") or []),
        )
        for envelope in (data or {}).get("envelopes") or []
    ]


async def read(
    account: MailAccount, password: str, folder: str, message_id: str
) -> MessageDetail:
    # Without --seen the message keeps its flags, so reading leaves it unread.
    raw = await himalaya.run(
        account,
        password,
        ["message", "read", f"--mailbox={folder}", "--raw", "--", message_id],
        json_output=False,
    )
    if len(raw) > MAX_MESSAGE_BYTES:
        raise MailError(f"Message {message_id} is larger than 30 MB and was not opened")
    if not raw:
        raise MailError(f"No message {message_id} in {folder}")
    return parse(raw, message_id, folder)


async def save_draft(account: MailAccount, password: str, msg: EmailMessage) -> str:
    folder = await special_mailbox(account, password, "drafts")
    if folder is None:
        raise MailError("This mailbox has no Drafts folder")
    await himalaya.run(
        account,
        password,
        ["message", "add", f"--mailbox={folder}", "--flag=draft", "--flag=seen"],
        stdin=msg.as_bytes(),
    )
    return folder


async def send(account: MailAccount, password: str, msg: EmailMessage) -> str | None:
    """Send, then file a copy in Sent unless the provider files its own.

    A failure to file the copy is logged, not raised: the mail is already out,
    and an error here would invite sending it again.
    """
    data = msg.as_bytes()
    await himalaya.run(account, password, ["message", "send", "--no-save"], stdin=data)
    if not account.append_sent:
        return None
    try:
        folder = await special_mailbox(account, password, "sent")
        if folder is None:
            return None
        await himalaya.run(
            account,
            password,
            ["message", "add", f"--mailbox={folder}", "--flag=seen"],
            stdin=data,
        )
    except MailError as e:
        logger.warning(f"Sent mail but could not file a copy in Sent: {e}")
        return None
    return folder


async def check(account: MailAccount, password: str) -> dict:
    """Sign in to IMAP and SMTP; never sends mail."""
    try:
        report = await himalaya.run(account, password, ["account", "check"])
        failed = [
            f"{b.get('backend')}: {b.get('error')}"
            for b in (report or {}).get("backends") or []
            if not b.get("ok")
        ]
        if failed:
            return {"ok": False, "error": "; ".join(failed)}
        mailboxes = await list_mailboxes(account, password)
    except MailError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "folders": [m.get("name", "") for m in mailboxes]}
