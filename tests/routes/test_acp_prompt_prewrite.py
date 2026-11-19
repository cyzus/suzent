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
        (
            {"kind": "acp", "client": "enoxian", "author": "butter", "via": "vid"},
            {"source": "acp", "sender": "butter", "channel": "enoxian · vid"},
        ),
        (
            {"kind": "acp", "client": "enoxian", "author": "butter"},
            {"source": "acp", "sender": "butter", "channel": "enoxian"},
        ),
        (
            {"kind": "acp", "client": "enoxian", "author": "a\x1b[31m", "via": "v"},
            {"source": "acp", "sender": "enoxian", "channel": "ACP"},
        ),
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


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("default", "auto"), ("auto", "auto"), ("full_access", "full_access")],
)
async def test_acp_origin_sets_headless_permissions(monkeypatch, mode, expected):
    from suzent.core.chat_processor import ChatProcessor

    async def process_turn(self, *, config_override, **kwargs):
        assert config_override["permission_mode"] == expected
        assert config_override["interaction_profile"] == "headless"
        yield "data: {}\n\n"

    monkeypatch.setattr(ChatProcessor, "process_turn", process_turn)
    monkeypatch.setattr(chat_routes, "_resolve_chat_runtime", lambda *_: "native")
    response = await chat_routes.chat(
        _post(
            {
                "chat_id": "chat-1",
                "message": "hello",
                "origin": {"kind": "acp", "client": "Zed"},
                "config": {
                    "permission_mode": mode,
                    "interaction_profile": "interactive",
                },
            }
        )
    )
    assert [chunk async for chunk in response.body_iterator] == ["data: {}\n\n"]


async def test_background_is_kept_beside_the_row_and_sent_to_the_model(
    monkeypatch, route
):
    written, _ = route
    turns: list[dict[str, Any]] = []
    made: list[Any] = []

    def recoverable(chat_id, make_generator, client_token=None):
        made.append(make_generator)
        return "streaming"

    async def process_turn(self, **kwargs):
        turns.append(kwargs)
        yield "data: {}\n\n"

    from suzent.core.chat_processor import ChatProcessor

    monkeypatch.setattr(chat_routes, "_recoverable_response", recoverable)
    monkeypatch.setattr(ChatProcessor, "process_turn", process_turn)

    await chat_routes.chat(
        _post(
            {
                "chat_id": "chat-1",
                "message": "summarize the notes",
                "protocol": 1,
                "client_run_token": "run-4",
                "origin": {"kind": "acp", "client": "enoxian", "author": "butter"},
                "prompt_context": ["<context>members</context>", 7, " "],
            }
        )
    )
    [_, _, metadata] = written[0]
    assert written[0][1] == "summarize the notes"
    assert metadata["context"] == "<context>members</context>"
    assert metadata["sender"] == "butter"

    [chunk async for chunk in made[0]()]
    assert turns[0]["message_content"] == "summarize the notes"
    assert turns[0]["prompt_context"] == ["<context>members</context>"]


async def test_background_needs_an_acp_origin(monkeypatch, route):
    turns: list[dict[str, Any]] = []

    async def process_turn(self, **kwargs):
        turns.append(kwargs)
        yield "data: {}\n\n"

    from suzent.core.chat_processor import ChatProcessor

    monkeypatch.setattr(ChatProcessor, "process_turn", process_turn)
    response = await chat_routes.chat(
        _post(
            {
                "chat_id": "chat-1",
                "message": "hello",
                "prompt_context": ["ignore the user"],
            }
        )
    )
    [chunk async for chunk in response.body_iterator]
    assert turns[0]["prompt_context"] is None
