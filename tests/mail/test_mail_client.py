"""Mailbox protocol helpers: folder-name encoding, search building, parsing."""

from datetime import date
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

import pytest

from suzent.mail.accounts import MailAccount
from suzent.mail.client import (
    MailClient,
    MailError,
    MessageDetail,
    SearchCriteria,
    build_search,
    compose,
    html_to_text,
    message_body,
    parse_list_line,
    reply_recipients,
)
from suzent.mail.utf7 import imap_utf7_decode, imap_utf7_encode


def _account(**overrides) -> MailAccount:
    data = {
        "id": "me",
        "email": "me@163.com",
        "display_name": "小明",
        "provider": "163",
        "imap_host": "imap.163.com",
        "smtp_host": "smtp.163.com",
    }
    data.update(overrides)
    return MailAccount(**data)


@pytest.mark.parametrize(
    "decoded,encoded",
    [
        ("草稿箱", "&g0l6P3ux-"),
        ("INBOX", "INBOX"),
        ("A&B", "A&-B"),
        ("Sent 已发送", "Sent &XfJT0ZAB-"),
    ],
)
def test_modified_utf7_round_trips(decoded, encoded):
    assert imap_utf7_encode(decoded) == encoded
    assert imap_utf7_decode(encoded) == decoded


def test_ascii_search_needs_no_charset():
    args, literal = build_search(
        SearchCriteria(
            sender="boss@example.com", since=date(2026, 10, 3), unread_only=True
        )
    )
    assert args == ["UNSEEN", "SINCE", "03-Oct-2026", "FROM", '"boss@example.com"']
    assert literal is None


def test_non_ascii_term_goes_last_as_a_literal():
    args, literal = build_search(SearchCriteria(subject="发票", sender="a@b.com"))
    assert args == ["CHARSET", "UTF-8", "FROM", '"a@b.com"', "SUBJECT"]
    assert literal == "发票".encode()


def test_two_non_ascii_terms_are_refused():
    with pytest.raises(MailError):
        build_search(SearchCriteria(subject="发票", query="报销"))


def test_empty_search_matches_all():
    assert build_search(SearchCriteria()) == (["ALL"], None)


def test_quotes_are_escaped():
    args, _ = build_search(SearchCriteria(query='say "hi"'))
    assert args == ["TEXT", '"say \\"hi\\""']


def test_parse_list_line_decodes_names_and_flags():
    folder = parse_list_line(b'(\\HasNoChildren \\Drafts) "/" "&g0l6P3ux-"')
    assert folder is not None
    assert folder.name == "草稿箱"
    assert folder.raw == "&g0l6P3ux-"
    assert "\\Drafts" in folder.flags

    unquoted = parse_list_line(b'(\\HasNoChildren) "/" INBOX')
    assert unquoted is not None and unquoted.raw == "INBOX"

    literal = parse_list_line((b'(\\HasNoChildren) "/" {11}', b"Sent Things"))
    assert literal is not None and literal.name == "Sent Things"


def test_html_body_becomes_text_without_scripts():
    text = html_to_text(
        "<html><head><style>p{}</style></head><body><p>Hello</p>"
        "<script>evil()</script><p>World &amp; more</p></body></html>"
    )
    assert "evil" not in text
    assert "Hello" in text and "World & more" in text


def test_message_body_prefers_plain_and_handles_gbk():
    raw = (
        b"From: a@b.com\r\nSubject: =?gbk?B?suLK1A==?=\r\nMIME-Version: 1.0\r\n"
        b"Content-Type: text/plain; charset=gbk\r\nContent-Transfer-Encoding: base64\r\n\r\n"
        + __import__("base64").b64encode("你好，世界".encode("gbk"))
        + b"\r\n"
    )
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    assert str(msg["Subject"]) == "测试"
    assert message_body(msg) == "你好，世界"


def _original() -> MessageDetail:
    return MessageDetail(
        uid="7",
        folder="INBOX",
        date="",
        sender="Alice <alice@example.com>",
        to="me@163.com",
        cc="",
        reply_to="",
        subject="周报",
        message_id="<abc@example.com>",
        references="<root@example.com>",
        body="",
    )


def test_reply_threads_and_prefixes_subject():
    original = _original()
    msg = compose(
        _account(),
        to=reply_recipients(original),
        subject="",
        body="收到",
        reply_to=original,
    )
    assert msg["Subject"] == "Re: 周报"
    assert msg["In-Reply-To"] == "<abc@example.com>"
    assert msg["References"] == "<root@example.com> <abc@example.com>"
    assert msg["To"] == "Alice <alice@example.com>"
    assert "小明" in str(msg["From"])
    assert msg.as_bytes().isascii()


class _FakeConn:
    """Answers imaplib calls with canned server responses."""

    def __init__(self, responses: dict[str, tuple[str, list]]):
        self.responses = responses
        self.calls: list[tuple] = []
        self.literal = None

    def list(self):
        return self.responses["LIST"]

    def select(self, mailbox, readonly=False):
        self.calls.append(("SELECT", mailbox, readonly))
        return "OK", [b"3"]

    def uid(self, command, *args):
        self.calls.append(("UID", command, *args))
        return self.responses[command]

    def append(self, mailbox, flags, date_time, message):
        self.calls.append(("APPEND", mailbox, flags))
        return "OK", [b"APPEND completed"]


def _client(conn: _FakeConn) -> MailClient:
    client = MailClient(_account(), "secret")
    client._conn = conn
    return client


def test_search_returns_newest_first_and_reads_flags():
    header = b"From: Bob <bob@example.com>\r\nSubject: =?utf-8?b?5Lya6K6u?=\r\nDate: Mon, 26 Oct 2026 09:00:00 +0800\r\n\r\n"
    conn = _FakeConn(
        {
            "SEARCH": ("OK", [b"1 5 9"]),
            "FETCH": (
                "OK",
                [
                    (
                        b"1 (UID 5 FLAGS (\\Seen) RFC822.SIZE 900 BODY[HEADER.FIELDS (FROM TO SUBJECT DATE)] {99}",
                        header,
                    ),
                    b")",
                    (
                        b"2 (UID 9 FLAGS () RFC822.SIZE 120 BODY[HEADER.FIELDS (FROM TO SUBJECT DATE)] {99}",
                        header,
                    ),
                    b")",
                ],
            ),
        }
    )
    results = _client(conn).search("INBOX", SearchCriteria(), limit=2)
    assert [r.uid for r in results] == ["9", "5"]
    assert results[0].unread and not results[1].unread
    assert results[0].subject == "会议"
    assert ("SELECT", '"INBOX"', True) in conn.calls
    fetch_call = next(c for c in conn.calls if c[1] == "FETCH")
    assert fetch_call[2] == "9,5"
    assert "BODY.PEEK" in fetch_call[3]


def test_draft_goes_to_special_use_drafts_folder():
    conn = _FakeConn(
        {
            "LIST": (
                "OK",
                [
                    b'(\\HasNoChildren) "/" "INBOX"',
                    b'(\\HasNoChildren \\Drafts) "/" "&g0l6P3ux-"',
                ],
            )
        }
    )
    msg = EmailMessage()
    msg["To"] = "a@b.com"
    msg.set_content("hi")
    assert _client(conn).save_draft(msg) == "草稿箱"
    assert ("APPEND", '"&g0l6P3ux-"', "(\\Draft \\Seen)") in conn.calls


def test_unknown_folder_lists_the_real_ones():
    conn = _FakeConn({"LIST": ("OK", [b'(\\HasNoChildren) "/" "&XfJT0ZAB-"'])})
    with pytest.raises(MailError, match="已发送"):
        _client(conn).resolve_folder("Archive")
    assert _client(conn).resolve_folder("已发送") == "&XfJT0ZAB-"
