"""Build outgoing messages and turn fetched ones into text for the model."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import formataddr, formatdate, getaddresses, make_msgid
from html.parser import HTMLParser

from .accounts import MailAccount


@dataclass
class MessageDetail:
    id: str
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
    except (ValueError, LookupError):
        return ""
    return str(value) if value is not None else ""


def parse(raw: bytes, message_id: str, folder: str) -> MessageDetail:
    msg = BytesParser(policy=policy.default).parsebytes(raw)
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
        id=message_id,
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


def compose(
    account: MailAccount,
    *,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    reply_to: MessageDetail | None = None,
) -> EmailMessage:
    msg = EmailMessage(policy=policy.SMTP)
    msg["From"] = formataddr((account.display_name, account.email))
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    # himalaya delivers to Bcc and strips the header before sending.
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
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
