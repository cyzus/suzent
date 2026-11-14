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
SEARCH_PAGE_SIZE = 50
# Paging stops at mail already seen; this caps one check's search.
MAX_PAGES = 10
# Mail older than this when a check finally runs (after the app was off a
# long while) is not reported.
MAX_LOOKBACK_DAYS = 7
# A burst beyond this waits for the next check, so one check stays short.
MAX_REPORTED_PER_CHECK = 20
# Enough ids to recognise everything a search can return again.
MAX_REMEMBERED = 500
PREVIEW_CHARS = 1500


async def check_inboxes(ctx: PluginContext) -> None:
    """Report mail that arrived since the last check, for every watched account."""
    for account in accounts.list_accounts():
        if not account.watch_inbox:
            # Forgetting what was seen makes switching it back on start from
            # a fresh baseline, rather than reporting mail from the gap.
            if ctx.state.get(_seen_key(account)) is not None:
                ctx.state.delete(_seen_key(account))
                ctx.state.delete(_checked_key(account))
            continue
        try:
            await _check_account(ctx, account)
        except Exception as exc:
            ctx.logger.warning(
                "Could not check the inbox of {}: {}", account.email, exc
            )


def _seen_key(account: MailAccount) -> str:
    return f"seen:{account.id}"


def _checked_key(account: MailAccount) -> str:
    return f"checked:{account.id}"


def _since(last_checked: str | None) -> date:
    """Search back to the day before the last complete check, within the lookback limit."""
    today = date.today()
    oldest = today - timedelta(days=MAX_LOOKBACK_DAYS)
    if not last_checked:
        return today - timedelta(days=1)
    try:
        return max(date.fromisoformat(last_checked) - timedelta(days=1), oldest)
    except ValueError:
        return today - timedelta(days=1)


async def _search_back_to(
    account: MailAccount, password: str, since: date, known: set[str]
) -> list[mailbox.MessageSummary]:
    """Mail since ``since``, newest first, paging until reaching mail already seen."""
    found: list[mailbox.MessageSummary] = []
    for page in range(1, MAX_PAGES + 1):
        batch = await mailbox.search(
            account,
            password,
            INBOX,
            SearchCriteria(since=since),
            SEARCH_PAGE_SIZE,
            page=page,
        )
        found.extend(batch)
        if len(batch) < SEARCH_PAGE_SIZE or any(m.id in known for m in batch):
            break
    return found


async def _check_account(ctx: PluginContext, account: MailAccount) -> None:
    if not accounts.has_credentials(account):
        return
    try:
        password = await accounts.resolve_credential(account)
    except Exception:
        return
    seen: list[str] | None = ctx.state.get(_seen_key(account))
    known = set(seen or [])
    found = await _search_back_to(
        account, password, _since(ctx.state.get(_checked_key(account))), known
    )
    today = date.today().isoformat()
    if seen is None:
        # The first check after turning it on only notes what is already
        # there, so turning it on doesn't report old mail.
        ctx.state.set(_seen_key(account), [m.id for m in found][:MAX_REMEMBERED])
        ctx.state.set(_checked_key(account), today)
        return
    # Search returns newest first; report oldest first.
    unseen = [m for m in reversed(found) if m.id not in known]
    for message in unseen[:MAX_REPORTED_PER_CHECK]:
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
    if len(unseen) <= MAX_REPORTED_PER_CHECK:
        # Only a check that reported everything moves the search window on;
        # a capped one leaves the rest for the next check to find.
        ctx.state.set(_checked_key(account), today)


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
