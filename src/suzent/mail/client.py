"""Blocking IMAP/SMTP operations on one mailbox, using only the standard library.

Tools call these from pydantic-ai's worker threads, so they stay synchronous.
Messages are always fetched with BODY.PEEK so reading never marks mail as read.
"""

from __future__ import annotations

import imaplib
import re
import smtplib
import ssl
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import formataddr, formatdate, getaddresses, make_msgid
from html.parser import HTMLParser

from suzent.logger import get_logger
from suzent.mail.accounts import MailAccount
from suzent.mail.utf7 import imap_utf7_decode

logger = get_logger(__name__)

TIMEOUT_SECONDS = 30
MAX_MESSAGE_BYTES = 30 * 1024 * 1024
_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

imaplib.Commands.setdefault("ID", ("NONAUTH", "AUTH", "SELECTED"))

_DRAFT_NAMES = ("drafts", "draft", "草稿箱", "草稿", "[gmail]/drafts")
_SENT_NAMES = (
    "sent",
    "sent messages",
    "sent items",
    "sent mail",
    "已发送",
    "[gmail]/sent mail",
)


class MailError(Exception):
    """A mailbox operation failed; the message is safe to show the user."""


# What a mailbox operation can raise for reasons outside Suzent's control: a
# dropped connection, a timeout, or a server answering NO/BAD mid-session.
MAIL_FAILURES = (MailError, imaplib.IMAP4.error, OSError)


@dataclass
class Folder:
    name: str
    raw: str
    flags: tuple[str, ...]


@dataclass
class MessageSummary:
    uid: str
    date: str
    sender: str
    to: str
    subject: str
    unread: bool
    size: int


@dataclass
class MessageDetail:
    uid: str
    folder: str
    date: str
    sender: str
    to: str
    cc: str
    reply_to: str
    subject: str
    message_id: str
    references: str
    body: str
    attachments: list[dict] = field(default_factory=list)


@dataclass
class SearchCriteria:
    query: str | None = None
    sender: str | None = None
    subject: str | None = None
    since: date | None = None
    unread_only: bool = False


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _imap_date(value: date) -> str:
    return f"{value.day:02d}-{_MONTHS[value.month - 1]}-{value.year}"


def build_search(criteria: SearchCriteria) -> tuple[list[str], bytes | None]:
    """IMAP SEARCH arguments, plus the one UTF-8 literal imaplib can send.

    imaplib attaches a literal to the end of the command, so the single
    non-ASCII term is placed last. Two non-ASCII terms cannot be sent together.
    """
    args: list[str] = []
    if criteria.unread_only:
        args.append("UNSEEN")
    if criteria.since:
        args += ["SINCE", _imap_date(criteria.since)]
    literal: bytes | None = None
    deferred: tuple[str, str] | None = None
    for key, value in (
        ("FROM", criteria.sender),
        ("SUBJECT", criteria.subject),
        ("TEXT", criteria.query),
    ):
        if not value:
            continue
        if value.isascii():
            args += [key, _quote(value)]
        elif deferred is None:
            deferred = (key, value)
        else:
            raise MailError(
                "Only one search term may contain non-ASCII text (such as Chinese). "
                "Search with one, then narrow the results."
            )
    if deferred:
        args.append(deferred[0])
        literal = deferred[1].encode("utf-8")
        args = ["CHARSET", "UTF-8", *args]
    return args or ["ALL"], literal


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "head", "title"}
    _BREAK = {
        "br",
        "p",
        "div",
        "tr",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "table",
        "blockquote",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BREAK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _part_text(part: Message) -> str:
    try:
        return part.get_content()
    except (LookupError, UnicodeDecodeError, AssertionError):
        payload = part.get_payload(decode=True) or b""
        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")


def message_body(msg: EmailMessage) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    text = _part_text(part)
    if part.get_content_type() == "text/html":
        text = html_to_text(text)
    return text.strip()


def _header(msg: Message, name: str) -> str:
    try:
        value = msg.get(name)
    except Exception:
        return ""
    return str(value) if value is not None else ""


def parse_list_line(line: bytes | tuple) -> Folder | None:
    if isinstance(line, tuple):
        head, name_bytes = line[0], line[1]
        match = re.match(rb"\((?P<flags>[^)]*)\)", head)
        raw = name_bytes.decode("ascii", errors="replace")
    else:
        match = re.match(
            rb'\((?P<flags>[^)]*)\) (?:"(?:[^"\\]|\\.)*"|NIL) (?P<name>.+)$', line
        )
        if not match:
            return None
        raw = match.group("name").decode("ascii", errors="replace").strip()
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if not match:
        return None
    flags = tuple(match.group("flags").decode("ascii", errors="replace").split())
    return Folder(name=imap_utf7_decode(raw), raw=raw, flags=flags)


def _parse_fetch(data: list) -> list[tuple[bytes, bytes]]:
    """Pairs of (fetch metadata, literal) from an imaplib FETCH response."""
    return [(item[0], item[1]) for item in data if isinstance(item, tuple)]


def _check(status: str, data: list, action: str) -> None:
    if status != "OK":
        detail = b" ".join(d for d in data if isinstance(d, bytes)).decode(
            "utf-8", errors="replace"
        )
        raise MailError(f"{action} failed: {detail or status}")


def _friendly_login_error(account: MailAccount, error: Exception) -> MailError:
    detail = error.args[-1] if error.args else error
    text = (
        detail.decode("utf-8", errors="replace")
        if isinstance(detail, bytes)
        else str(detail)
    )
    hint = (
        "Check the address and use an app password or authorization code "
        "(授权码) from the mailbox's settings, not the normal login password. "
        "IMAP must also be switched on in the mailbox's settings."
    )
    if "unsafe login" in text.lower():
        hint = "NetEase blocked the login as unsafe; " + hint
    return MailError(
        f"Could not sign in to {account.imap_host}: {text.rstrip('.')}. {hint}"
    )


class MailClient:
    """One IMAP session. Use as a context manager."""

    def __init__(self, account: MailAccount, password: str) -> None:
        self.account = account
        self._password = password
        self._conn: imaplib.IMAP4_SSL | None = None
        self._folders: list[Folder] | None = None

    def __enter__(self) -> MailClient:
        context = ssl.create_default_context()
        try:
            conn = imaplib.IMAP4_SSL(
                self.account.imap_host,
                self.account.imap_port,
                ssl_context=context,
                timeout=TIMEOUT_SECONDS,
            )
        except OSError as e:
            raise MailError(
                f"Could not reach {self.account.imap_host}:{self.account.imap_port}: {e}"
            ) from e
        try:
            conn.login(self.account.login, self._password)
        except imaplib.IMAP4.error as e:
            conn.shutdown()
            raise _friendly_login_error(self.account, e) from e
        if self.account.needs_imap_id:
            try:
                conn._simple_command(
                    "ID", '("name" "Suzent" "version" "1.0" "vendor" "Suzent")'
                )
            except imaplib.IMAP4.error as e:
                logger.debug(f"IMAP ID rejected by {self.account.imap_host}: {e}")
        self._conn = conn
        return self

    def __exit__(self, *exc) -> None:
        if self._conn is None:
            return
        try:
            self._conn.logout()
        except Exception:
            pass
        self._conn = None

    @property
    def conn(self) -> imaplib.IMAP4_SSL:
        if self._conn is None:
            raise MailError("Mailbox is not connected")
        return self._conn

    def list_folders(self) -> list[Folder]:
        if self._folders is None:
            status, data = self.conn.list()
            _check(status, data, "Listing folders")
            self._folders = [
                f for f in (parse_list_line(line) for line in data if line) if f
            ]
        return self._folders

    def resolve_folder(self, name: str) -> str:
        """The wire name for a folder given by its display name or wire name."""
        if name.upper() == "INBOX":
            return "INBOX"
        for folder in self.list_folders():
            if name in (folder.name, folder.raw):
                return folder.raw
        lowered = name.lower()
        for folder in self.list_folders():
            if folder.name.lower() == lowered:
                return folder.raw
        raise MailError(
            f"No folder '{name}'. Folders: "
            + ", ".join(f.name for f in self.list_folders())
        )

    def special_folder(self, flag: str, fallback_names: tuple[str, ...]) -> str | None:
        folders = self.list_folders()
        for folder in folders:
            if flag in folder.flags:
                return folder.raw
        for folder in folders:
            if folder.name.lower() in fallback_names:
                return folder.raw
        return None

    def _select(self, folder: str) -> str:
        raw = self.resolve_folder(folder)
        status, data = self.conn.select(_quote(raw), readonly=True)
        _check(status, data, f"Opening folder {folder}")
        return raw

    def search(
        self, folder: str, criteria: SearchCriteria, limit: int
    ) -> list[MessageSummary]:
        self._select(folder)
        args, literal = build_search(criteria)
        if literal is not None:
            self.conn.literal = literal
        status, data = self.conn.uid("SEARCH", *args)
        _check(status, data, "Searching")
        uids = (data[0] or b"").split()
        newest = list(reversed(uids[-limit:])) if limit > 0 else []
        if not newest:
            return []
        status, data = self.conn.uid(
            "FETCH",
            b",".join(newest).decode(),
            "(UID FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)])",
        )
        _check(status, data, "Fetching headers")
        parser = BytesParser(policy=policy.default)
        by_uid: dict[str, MessageSummary] = {}
        for meta, header_bytes in _parse_fetch(data):
            uid_match = re.search(rb"UID (\d+)", meta)
            if not uid_match:
                continue
            flags_match = re.search(rb"FLAGS \(([^)]*)\)", meta)
            size_match = re.search(rb"RFC822\.SIZE (\d+)", meta)
            headers = parser.parsebytes(header_bytes, headersonly=True)
            uid = uid_match.group(1).decode()
            by_uid[uid] = MessageSummary(
                uid=uid,
                date=_header(headers, "Date"),
                sender=_header(headers, "From"),
                to=_header(headers, "To"),
                subject=_header(headers, "Subject"),
                unread=b"\\Seen" not in (flags_match.group(1) if flags_match else b""),
                size=int(size_match.group(1)) if size_match else 0,
            )
        return [by_uid[u.decode()] for u in newest if u.decode() in by_uid]

    def fetch(self, folder: str, uid: str) -> MessageDetail:
        if not uid.isdigit():
            raise MailError(f"Invalid message uid '{uid}'")
        self._select(folder)
        status, data = self.conn.uid("FETCH", uid, "(RFC822.SIZE)")
        _check(status, data, "Fetching message")
        size_match = re.search(
            rb"RFC822\.SIZE (\d+)", b" ".join(d for d in data if isinstance(d, bytes))
        )
        if not size_match:
            raise MailError(f"No message with uid {uid} in {folder}")
        if int(size_match.group(1)) > MAX_MESSAGE_BYTES:
            raise MailError(f"Message {uid} is larger than 30 MB and was not opened")
        status, data = self.conn.uid("FETCH", uid, "(BODY.PEEK[])")
        _check(status, data, "Fetching message")
        pairs = _parse_fetch(data)
        if not pairs:
            raise MailError(f"No message with uid {uid} in {folder}")
        msg = BytesParser(policy=policy.default).parsebytes(pairs[0][1])
        attachments = []
        for part in msg.iter_attachments():
            payload = part.get_payload(decode=True) or b""
            attachments.append(
                {
                    "filename": part.get_filename() or "(unnamed)",
                    "content_type": part.get_content_type(),
                    "size": len(payload),
                }
            )
        return MessageDetail(
            uid=uid,
            folder=folder,
            date=_header(msg, "Date"),
            sender=_header(msg, "From"),
            to=_header(msg, "To"),
            cc=_header(msg, "Cc"),
            reply_to=_header(msg, "Reply-To"),
            subject=_header(msg, "Subject"),
            message_id=_header(msg, "Message-ID"),
            references=_header(msg, "References"),
            body=message_body(msg),
            attachments=attachments,
        )

    def append(self, folder_raw: str, msg: EmailMessage, flags: str) -> None:
        status, data = self.conn.append(
            _quote(folder_raw),
            flags,
            imaplib.Time2Internaldate(time.time()),
            msg.as_bytes(policy=policy.SMTP),
        )
        _check(status, data, f"Saving to {imap_utf7_decode(folder_raw)}")

    def save_draft(self, msg: EmailMessage) -> str:
        folder = self.special_folder("\\Drafts", _DRAFT_NAMES)
        if folder is None:
            raise MailError("This mailbox has no Drafts folder")
        self.append(folder, msg, "(\\Draft \\Seen)")
        return imap_utf7_decode(folder)

    def save_sent(self, msg: EmailMessage) -> str | None:
        folder = self.special_folder("\\Sent", _SENT_NAMES)
        if folder is None:
            return None
        self.append(folder, msg, "(\\Seen)")
        return imap_utf7_decode(folder)


def compose(
    account: MailAccount,
    *,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    reply_to: MessageDetail | None = None,
) -> EmailMessage:
    msg = EmailMessage(policy=policy.SMTP)
    msg["From"] = formataddr((account.display_name, account.email))
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if reply_to is not None:
        if not subject:
            original = reply_to.subject
            subject = (
                original if original.lower().startswith("re:") else f"Re: {original}"
            )
        if reply_to.message_id:
            msg["In-Reply-To"] = reply_to.message_id
            msg["References"] = " ".join(
                p for p in (reply_to.references, reply_to.message_id) if p
            )
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=account.email.rpartition("@")[2] or None)
    # Base64 keeps non-ASCII bodies 7-bit clean for servers without 8BITMIME.
    msg.set_content(body, cte=None if body.isascii() else "base64")
    return msg


def reply_recipients(original: MessageDetail) -> list[str]:
    source = original.reply_to or original.sender
    return [formataddr(pair) for pair in getaddresses([source]) if pair[1]]


def all_recipients(msg: EmailMessage, bcc: list[str]) -> list[str]:
    fields = [msg.get_all(name, []) for name in ("To", "Cc")]
    addresses = getaddresses([str(v) for values in fields for v in values] + bcc)
    return [addr for _, addr in addresses if addr]


@contextmanager
def _smtp_session(account: MailAccount, password: str) -> Iterator[smtplib.SMTP]:
    context = ssl.create_default_context()
    try:
        if account.smtp_security == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                account.smtp_host,
                account.smtp_port,
                timeout=TIMEOUT_SECONDS,
                context=context,
            )
        else:
            server = smtplib.SMTP(
                account.smtp_host, account.smtp_port, timeout=TIMEOUT_SECONDS
            )
            server.starttls(context=context)
        with server:
            server.login(account.login, password)
            yield server
    except smtplib.SMTPAuthenticationError as e:
        raise _friendly_login_error(account, e) from e
    except (smtplib.SMTPException, OSError) as e:
        raise MailError(f"SMTP with {account.smtp_host} failed: {e}") from e


def send(
    account: MailAccount, password: str, msg: EmailMessage, bcc: list[str]
) -> None:
    recipients = all_recipients(msg, bcc)
    if not recipients:
        raise MailError("The message has no recipients")
    with _smtp_session(account, password) as server:
        server.send_message(msg, from_addr=account.email, to_addrs=recipients)


def check_account(account: MailAccount, password: str) -> dict:
    """Sign in to IMAP and SMTP; never sends mail."""
    try:
        with MailClient(account, password) as client:
            folders = client.list_folders()
        with _smtp_session(account, password):
            pass
    except MAIL_FAILURES as e:
        return {"ok": False, "error": str(e) or e.__class__.__name__}
    return {"ok": True, "folders": [f.name for f in folders]}
