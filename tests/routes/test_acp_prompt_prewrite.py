"""/chat writes an ACP client's prompt to the transcript before its turn.

The ACP server posts each prompt to /chat on the client's behalf. That route
wrote nothing for it and registered no live stream, so the desktop showed the
reply with no sign of what was asked, or of who asked it -- unlike a session
Regent starts, whose request is on screen from the first moment.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from starlette.requests import Request

from suzent.routes import chat_routes


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        (
            {"kind": "acp", "client": "Zed"},
            {"source": "acp", "sender": "Zed", "channel": "ACP"},
        ),
        (
            {"kind": "acp", "client": "evil\x1b[31m"},
            {"source": "acp", "sender": "ACP client", "channel": "ACP"},
        ),
        (
            {"kind": "acp", "client": "x" * 101},
            {"source": "acp", "sender": "ACP client", "channel": "ACP"},
        ),
        ({"kind": "acp"}, {"source": "acp", "sender": "ACP client", "channel": "ACP"}),
        ({"kind": "something-else", "client": "Zed"}, None),
        ("acp", None),
        (None, None),
    ],
)
def test_only_a_printable_client_name_reaches_the_transcript(origin, expected):
    assert chat_routes._origin_metadata(origin) == expected


def _post(payload: dict[str, Any]) -> Request:
    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(payload).encode(),
            "more_body": False,
        }

    return Request(
        {"type": "http", "method": "POST", "path": "/chat", "headers": []}, receive
    )


@pytest.fixture
def route(monkeypatch: pytest.MonkeyPatch):
    written: list[tuple[str, str, dict | None]] = []
    started: list[str] = []

    def prewrite(
        chat_id, message, files=None, *, client_message_id=None, metadata=None
    ):
        written.append((chat_id, message, metadata))
        return message, True

    def recoverable(chat_id, make_generator, client_token=None):
        started.append(chat_id)
        return "streaming"

    monkeypatch.setattr(chat_routes, "prewrite_prompt", prewrite)
    monkeypatch.setattr(chat_routes, "_recoverable_response", recoverable)
    monkeypatch.setattr(chat_routes, "is_background_streaming", lambda chat_id: False)
    monkeypatch.setattr(
        chat_routes, "_resolve_chat_runtime", lambda chat_id, config: "native"
    )
    return written, started


async def test_an_acp_prompt_is_in_the_transcript_before_the_turn(route):
    written, started = route

    response = await chat_routes.chat(
        _post(
            {
                "chat_id": "chat-1",
                "message": "read a.py",
                "protocol": 1,
                "client_run_token": "run-1",
                "origin": {"kind": "acp", "client": "Zed"},
            }
        )
    )

    assert response == "streaming"
    assert started == ["chat-1"]
    assert written == [
        ("chat-1", "read a.py", {"source": "acp", "sender": "Zed", "channel": "ACP"})
    ]


async def test_resuming_an_approval_writes_no_second_prompt(route):
    written, _ = route

    await chat_routes.chat(
        _post(
            {
                "chat_id": "chat-1",
                "message": "",
                "protocol": 1,
                "client_run_token": "run-2",
                "origin": {"kind": "acp", "client": "Zed"},
                "resume_approvals": [{"approvalId": "a", "approved": True}],
            }
        )
    )

    assert written == []


async def test_a_prompt_with_no_origin_is_left_to_its_sender(route):
    written, _ = route

    await chat_routes.chat(
        _post(
            {
                "chat_id": "chat-1",
                "message": "hello",
                "protocol": 1,
                "client_run_token": "run-3",
            }
        )
    )

    assert written == []
