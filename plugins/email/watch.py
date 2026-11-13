"""Reporting new inbox mail to the Mailbox, for accounts with Watch inbox on."""

from __future__ import annotations

from datetime import date, timedelta
from email.utils import parseaddr

from suzent.plugins import PluginContext

from . import accounts, mailbox
from .accounts import MailAccount
from .mailbox import SearchCriteria

CHECK_EVERY_SECONDS = 300
INBOX = "INBOX"
# Each check looks at the last day of mail; this many is plenty for five minutes.
SEARCH_LIMIT = 50
# A burst beyond this waits for the next check, so one check stays short.
MAX_REPORTED_PER_CHECK = 20
# Enough ids to recognise everything a day's search can return again.
MAX_REMEMBERED = 500
PREVIEW_CHARS = 1500


async def check_inboxes(ctx: PluginContext) -> None:
    """Report mail that arrived since the last check, for every watched account."""
    for account in accounts.list_accounts():
        if not account.watch_inbox:
            continue
        try:
            await _check_account(ctx, account)
        except Exception as exc:
            ctx.logger.warning(
                "Could not check the inbox of {}: {}", account.email, exc
            )


def _seen_key(account: MailAccount) -> str:
    return f"seen:{account.id}"


async def _check_account(ctx: PluginContext, account: MailAccount) -> None:
    password = accounts.get_password(account)
    if not password:
        return
    found = await mailbox.search(
        account,
        password,
        INBOX,
        SearchCriteria(since=date.today() - timedelta(days=1)),
        SEARCH_LIMIT,
    )
    seen: list[str] | None = ctx.state.get(_seen_key(account))
    if seen is None:
        # The first check after turning it on only notes what is already
        # there, so turning it on doesn't report a day of old mail.
        ctx.state.set(_seen_key(account), [m.id for m in found][:MAX_REMEMBERED])
        return
    known = set(seen)
    # Search returns newest first; report oldest first.
    new = [m for m in reversed(found) if m.id not in known][:MAX_REPORTED_PER_CHECK]
    for message in new:
        await ctx.emit_event(
            event_type="message",
            summary=f"{message.sender} — {message.subject}",
            source_name=account.email,
            rule_key=f"{account.id}:{_sender_domain(message.sender)}",
            payload={
                "account": account.id,
                "folder": INBOX,
                "id": message.id,
                "from": message.sender,
                "subject": message.subject,
                "date": message.date,
                "preview": await _preview(account, password, message.id),
                "read_with": "mail_read, using this account, folder and id",
            },
        )
        # Saved after each one, so a failure partway never reports one twice.
        seen = [message.id, *seen][:MAX_REMEMBERED]
        ctx.state.set(_seen_key(account), seen)


def _sender_domain(sender: str) -> str:
    address = parseaddr(sender)[1]
    return address.rpartition("@")[2].lower() or "unknown"


async def _preview(account: MailAccount, password: str, message_id: str) -> str:
    """The start of the message body, read without marking it read."""
    try:
        detail = await mailbox.read(account, password, INBOX, message_id)
    except Exception:
        return ""
    body = " ".join(detail.body.split())
    return body[:PREVIEW_CHARS]
