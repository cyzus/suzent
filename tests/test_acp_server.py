"""Tests for serving Suzent as an ACP agent (``suzent acp``).

The backend is faked so these exercise the protocol translation itself: the
handshake, cwd binding, SSE-to-session/update mapping, the approval round trip
that gates a tool call, and cancellation.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from suzent.acp.server import (
    ACPAgentServer,
    PROTOCOL_VERSION,
    SESSION_MARKER,
    WORKSPACE_MOUNT,
    TurnTranslator,
    _permission_options,
    _prompt_text,
    tool_kind,
)


def sse(event: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(event)}\n\n".encode()


class FakeBackend:
    """Records what the ACP layer asked the backend to do."""

    def __init__(self, turns: list[list[bytes]], *, sandbox: bool = True):
        self.turns = turns
        self._sandbox = sandbox
        self.created: list[tuple[str, dict[str, Any]]] = []
        self.payloads: list[dict[str, Any]] = []
        self.stopped: list[str] = []
        self.chats: dict[str, dict[str, Any]] = {}

    async def sandbox_enabled(self) -> bool:
        return self._sandbox

    async def create_chat(self, title: str, config: dict[str, Any]) -> str:
        chat_id = f"chat-{len(self.created) + 1}"
        self.created.append((title, config))
        self.chats[chat_id] = {"id": chat_id, "config": config, "messages": []}
        return chat_id

    async def get_chat(self, chat_id: str) -> dict[str, Any] | None:
        return self.chats.get(chat_id)

    async def stream_turn(self, payload: dict[str, Any]):
        self.payloads.append(payload)
        for chunk in self.turns.pop(0) if self.turns else []:
            yield chunk

    async def stop_turn(self, chat_id: str) -> None:
        self.stopped.append(chat_id)

    async def aclose(self) -> None:
        return None


class Wire:
    """Collects everything the server sends to the client."""

    def __init__(self):
        self.sent: list[dict[str, Any]] = []
        self.responder = None

    async def __call__(self, message: dict[str, Any]) -> None:
        self.sent.append(message)
        if self.responder and message.get("method") and message.get("id") is not None:
            await self.responder(message)

    def updates(self) -> list[dict[str, Any]]:
        return [
            m["params"]["update"]
            for m in self.sent
            if m.get("method") == "session/update"
        ]

    def result(self, message_id: int) -> Any:
        for message in self.sent:
            if message.get("id") == message_id and "result" in message:
                return message["result"]
        return None

    def error(self, message_id: int) -> dict[str, Any] | None:
        for message in self.sent:
            if message.get("id") == message_id and "error" in message:
                return message["error"]
        return None


def request(message_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "method": method, "params": params}


# ── handshake and session binding ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_initialize_advertises_v1_and_resume(tmp_path):
    wire = Wire()
    server = ACPAgentServer(FakeBackend([]), wire)

    await server.dispatch(request(1, "initialize", {"clientCapabilities": {}}))

    result = wire.result(1)
    assert result["protocolVersion"] == PROTOCOL_VERSION
    assert result["agentCapabilities"]["loadSession"] is True
    assert result["agentInfo"]["name"] == "suzent"


@pytest.mark.asyncio
async def test_session_new_binds_the_client_cwd_as_a_mount(tmp_path):
    backend = FakeBackend([], sandbox=True)
    wire = Wire()
    server = ACPAgentServer(backend, wire)

    await server.dispatch(request(1, "initialize", {}))
    await server.dispatch(request(2, "session/new", {"cwd": str(tmp_path)}))

    assert wire.result(2) == {"sessionId": "chat-1"}
    _title, config = backend.created[0]
    assert config["sandbox_volumes"] == [f"{tmp_path.resolve()}:{WORKSPACE_MOUNT}"]
    # Sandbox turns run in the container, so the agent's cwd is the mount point.
    assert config["cwd"] == WORKSPACE_MOUNT
    assert config[SESSION_MARKER]["cwd"] == str(tmp_path.resolve())


@pytest.mark.asyncio
async def test_host_mode_session_uses_the_real_directory_as_cwd(tmp_path):
    backend = FakeBackend([], sandbox=False)
    server = ACPAgentServer(backend, Wire())

    await server.dispatch(request(1, "initialize", {}))
    await server.dispatch(request(2, "session/new", {"cwd": str(tmp_path)}))

    _title, config = backend.created[0]
    assert config["cwd"] == str(tmp_path.resolve())


@pytest.mark.asyncio
async def test_session_new_rejects_a_relative_cwd():
    wire = Wire()
    server = ACPAgentServer(FakeBackend([]), wire)

    await server.dispatch(request(1, "session/new", {"cwd": "relative/dir"}))

    assert "not absolute" in wire.error(1)["message"]


@pytest.mark.asyncio
async def test_session_load_refuses_a_chat_this_surface_did_not_create(tmp_path):
    backend = FakeBackend([])
    backend.chats["local-chat"] = {"id": "local-chat", "config": {}, "messages": []}
    wire = Wire()
    server = ACPAgentServer(backend, wire)

    await server.dispatch(request(1, "session/load", {"sessionId": "local-chat"}))

    assert "not an ACP session" in wire.error(1)["message"]


@pytest.mark.asyncio
async def test_session_load_replays_history(tmp_path):
    backend = FakeBackend([])
    wire = Wire()
    server = ACPAgentServer(backend, wire)
    await server.dispatch(request(1, "initialize", {}))
    await server.dispatch(request(2, "session/new", {"cwd": str(tmp_path)}))
    backend.chats["chat-1"]["messages"] = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]

    await server.dispatch(
        request(3, "session/load", {"sessionId": "chat-1", "cwd": str(tmp_path)})
    )

    kinds = [u["sessionUpdate"] for u in wire.updates()]
    assert kinds == ["user_message_chunk", "agent_message_chunk"]
    assert wire.error(3) is None


# ── one turn ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prompt_streams_text_and_tool_calls(tmp_path):
    backend = FakeBackend(
        [
            [
                sse({"type": "TEXT_MESSAGE_CONTENT", "delta": "Look"}),
                sse({"type": "THINKING_TEXT_MESSAGE_CONTENT", "delta": "hmm"}),
                sse(
                    {
                        "type": "TOOL_CALL_START",
                        "toolCallId": "t1",
                        "toolCallName": "read_file",
                    }
                ),
                sse(
                    {
                        "type": "TOOL_CALL_ARGS",
                        "toolCallId": "t1",
                        "delta": '{"path": "a.py"}',
                    }
                ),
                sse({"type": "TOOL_CALL_END", "toolCallId": "t1"}),
                sse(
                    {
                        "type": "TOOL_CALL_RESULT",
                        "toolCallId": "t1",
                        "content": "print(1)",
                    }
                ),
                sse({"type": "TEXT_MESSAGE_CONTENT", "delta": "ing"}),
                sse({"type": "AGENT_FINISHED"}),
            ]
        ]
    )
    wire = Wire()
    server = ACPAgentServer(backend, wire)
    await server.dispatch(request(1, "initialize", {}))
    await server.dispatch(request(2, "session/new", {"cwd": str(tmp_path)}))

    await server.dispatch(
        request(
            3,
            "session/prompt",
            {"sessionId": "chat-1", "prompt": [{"type": "text", "text": "read a.py"}]},
        )
    )
    await server.drain()

    assert wire.result(3) == {"stopReason": "end_turn"}
    updates = wire.updates()
    assert updates[0] == {
        "sessionUpdate": "agent_message_chunk",
        "content": {"type": "text", "text": "Look"},
    }
    assert updates[1]["sessionUpdate"] == "agent_thought_chunk"
    assert updates[2] == {
        "sessionUpdate": "tool_call",
        "toolCallId": "t1",
        "title": "read_file",
        "kind": "read",
        "status": "in_progress",
    }
    assert updates[3]["rawInput"] == {"path": "a.py"}
    assert updates[4]["status"] == "completed"
    assert updates[4]["content"][0]["content"]["text"] == "print(1)"
    # The turn text is what the backend streamed, and only the client's config
    # binding rides along with it.
    assert backend.payloads[0]["message"] == "read a.py"
    assert backend.payloads[0]["chat_id"] == "chat-1"


@pytest.mark.asyncio
async def test_prompt_reports_a_backend_run_error(tmp_path):
    backend = FakeBackend([[sse({"type": "RUN_ERROR", "message": "model exploded"})]])
    wire = Wire()
    server = ACPAgentServer(backend, wire)
    await server.dispatch(request(1, "initialize", {}))
    await server.dispatch(request(2, "session/new", {"cwd": str(tmp_path)}))

    await server.dispatch(
        request(
            3,
            "session/prompt",
            {"sessionId": "chat-1", "prompt": [{"type": "text", "text": "go"}]},
        )
    )
    await server.drain()

    assert wire.error(3)["message"] == "model exploded"


@pytest.mark.asyncio
async def test_prompt_on_an_unknown_session_is_an_error():
    wire = Wire()
    server = ACPAgentServer(FakeBackend([]), wire)

    await server.dispatch(
        request(
            1,
            "session/prompt",
            {"sessionId": "nope", "prompt": [{"type": "text", "text": "go"}]},
        )
    )
    await server.drain()

    assert "no such session" in wire.error(1)["message"]


# ── approvals ─────────────────────────────────────────────────────────────────


APPROVAL_EVENT = {
    "type": "CUSTOM",
    "name": "tool_approval_request",
    "value": {
        "approvalId": "a1",
        "toolCallId": "t1",
        "toolName": "run_command",
        "args": {"content": "git status"},
        "decision": {
            "actions": [
                {
                    "id": "allow_once",
                    "label": "Allow",
                    "behavior": "allow",
                    "scope": "once",
                },
                {
                    "id": "allow_global",
                    "label": "Always allow all git …",
                    "behavior": "allow",
                    "scope": "global",
                },
                {
                    "id": "reject",
                    "label": "Reject",
                    "behavior": "deny",
                    "scope": "once",
                },
            ]
        },
    },
}


def suspended_then_finished() -> list[list[bytes]]:
    return [
        [
            sse(
                {
                    "type": "TOOL_CALL_START",
                    "toolCallId": "t1",
                    "toolCallName": "run_command",
                }
            ),
            sse(APPROVAL_EVENT),
        ],
        [
            sse({"type": "TEXT_MESSAGE_CONTENT", "delta": "done"}),
        ],
    ]


@pytest.mark.asyncio
async def test_approval_becomes_a_client_permission_request(tmp_path):
    backend = FakeBackend(suspended_then_finished())
    wire = Wire()

    async def answer(message: dict[str, Any]) -> None:
        assert message["method"] == "session/request_permission"
        assert message["params"]["toolCall"]["rawInput"] == {"content": "git status"}
        await server.dispatch(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {
                    "outcome": {"outcome": "selected", "optionId": "allow_global"}
                },
            }
        )

    wire.responder = answer
    server = ACPAgentServer(backend, wire)
    await server.dispatch(request(1, "initialize", {}))
    await server.dispatch(request(2, "session/new", {"cwd": str(tmp_path)}))

    await server.dispatch(
        request(
            3,
            "session/prompt",
            {"sessionId": "chat-1", "prompt": [{"type": "text", "text": "status"}]},
        )
    )
    await server.drain()

    assert wire.result(3) == {"stopReason": "end_turn"}
    # The decision resumes the same turn, carrying the backend's own action id
    # so "always allow" persists the rule the option promised.
    resume = backend.payloads[1]["resume_approvals"]
    assert resume == [
        {
            "request_id": "a1",
            "tool_call_id": "t1",
            "approved": True,
            "action_id": "allow_global",
        }
    ]
    assert backend.payloads[1]["message"] == ""


@pytest.mark.asyncio
async def test_rejected_permission_resumes_as_a_denial(tmp_path):
    backend = FakeBackend(suspended_then_finished())
    wire = Wire()

    async def answer(message: dict[str, Any]) -> None:
        await server.dispatch(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {"outcome": {"outcome": "selected", "optionId": "reject"}},
            }
        )

    wire.responder = answer
    server = ACPAgentServer(backend, wire)
    await server.dispatch(request(1, "initialize", {}))
    await server.dispatch(request(2, "session/new", {"cwd": str(tmp_path)}))

    await server.dispatch(
        request(
            3,
            "session/prompt",
            {"sessionId": "chat-1", "prompt": [{"type": "text", "text": "status"}]},
        )
    )
    await server.drain()

    assert backend.payloads[1]["resume_approvals"][0]["approved"] is False


@pytest.mark.asyncio
async def test_cancelled_permission_stops_the_turn(tmp_path):
    backend = FakeBackend(suspended_then_finished())
    wire = Wire()

    async def answer(message: dict[str, Any]) -> None:
        await server.dispatch(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {"outcome": {"outcome": "cancelled"}},
            }
        )

    wire.responder = answer
    server = ACPAgentServer(backend, wire)
    await server.dispatch(request(1, "initialize", {}))
    await server.dispatch(request(2, "session/new", {"cwd": str(tmp_path)}))

    await server.dispatch(
        request(
            3,
            "session/prompt",
            {"sessionId": "chat-1", "prompt": [{"type": "text", "text": "status"}]},
        )
    )
    await server.drain()

    assert wire.result(3) == {"stopReason": "cancelled"}
    assert backend.stopped == ["chat-1"]


# ── cancellation ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_session_cancel_ends_the_turn_as_cancelled(tmp_path):
    wire = Wire()

    class SlowBackend(FakeBackend):
        async def stream_turn(self, payload):
            self.payloads.append(payload)
            yield sse({"type": "TEXT_MESSAGE_CONTENT", "delta": "start"})
            # The client cancels between frames, which is the realistic case:
            # a stop lands while the model is still producing.
            await server.dispatch(
                {
                    "jsonrpc": "2.0",
                    "method": "session/cancel",
                    "params": {"sessionId": "chat-1"},
                }
            )
            yield sse({"type": "TEXT_MESSAGE_CONTENT", "delta": " more"})

    backend = SlowBackend([])
    server = ACPAgentServer(backend, wire)
    await server.dispatch(request(1, "initialize", {}))
    await server.dispatch(request(2, "session/new", {"cwd": str(tmp_path)}))

    await server.dispatch(
        request(
            3,
            "session/prompt",
            {"sessionId": "chat-1", "prompt": [{"type": "text", "text": "go"}]},
        )
    )
    await server.drain()

    assert wire.result(3) == {"stopReason": "cancelled"}
    assert backend.stopped == ["chat-1"]
    texts = [u["content"]["text"] for u in wire.updates()]
    assert texts == ["start"]


@pytest.mark.asyncio
async def test_unknown_method_is_method_not_found():
    wire = Wire()
    server = ACPAgentServer(FakeBackend([]), wire)

    await server.dispatch(request(1, "session/teleport", {}))

    assert wire.error(1)["code"] == -32601


# ── translation units ─────────────────────────────────────────────────────────


def test_translator_handles_frames_split_across_chunks():
    translator = TurnTranslator()
    frame = sse({"type": "TEXT_MESSAGE_CONTENT", "delta": "hello"})
    assert list(translator.feed(frame[:12])) == []
    items = list(translator.feed(frame[12:]))
    assert items[0].payload["content"]["text"] == "hello"


def test_replayed_tool_call_start_updates_instead_of_duplicating():
    translator = TurnTranslator()
    start = sse(
        {"type": "TOOL_CALL_START", "toolCallId": "t1", "toolCallName": "edit_file"}
    )
    first = list(translator.feed(start))
    second = list(translator.feed(start))
    assert first[0].payload["sessionUpdate"] == "tool_call"
    assert second[0].payload == {
        "sessionUpdate": "tool_call_update",
        "toolCallId": "t1",
        "status": "in_progress",
    }


def test_prompt_text_flattens_content_blocks():
    text = _prompt_text(
        [
            {"type": "text", "text": "fix"},
            {"type": "resource_link", "uri": "file:///a.py"},
            {
                "type": "resource",
                "resource": {"uri": "file:///b.py", "text": "x = 1"},
            },
        ]
    )
    assert text == "fix\n\n@file:///a.py\n\nfile:///b.py\nx = 1"


def test_permission_options_derive_kinds_from_backend_scope():
    options = _permission_options(APPROVAL_EVENT["value"]["decision"])
    assert options == [
        {"optionId": "allow_once", "name": "Allow", "kind": "allow_once"},
        {
            "optionId": "allow_global",
            "name": "Always allow all git …",
            "kind": "allow_always",
        },
        {"optionId": "reject", "name": "Reject", "kind": "reject_once"},
    ]


def test_tool_kinds_cover_the_common_tools():
    assert tool_kind("read_file") == "read"
    assert tool_kind("edit_file") == "edit"
    assert tool_kind("run_command") == "execute"
    assert tool_kind("web_search") == "fetch"
    assert tool_kind("summon_daemon") == "other"
