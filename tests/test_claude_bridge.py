"""Tests for the built-in Claude CLI → ACP bridge."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from suzent.acp.claude_bridge import (
    ClaudeACPBridge,
    _Session,
    _cli_env,
    _extract_assistant_text,
    _extract_prompt_text,
    _extract_text_delta,
    _rejects_partial_messages,
    _try_capture_conversation_id,
)


# ── _extract_prompt_text ─────────────────────────────────────────────────────


def test_extract_prompt_text_typed_parts():
    parts = [
        {"type": "text", "text": "Hello"},
        {"type": "text", "text": "World"},
    ]
    assert _extract_prompt_text(parts) == "Hello\nWorld"


def test_extract_prompt_text_plain_strings():
    assert _extract_prompt_text(["one", "two"]) == "one\ntwo"


def test_extract_prompt_text_mixed():
    parts = [{"type": "text", "text": "first"}, "second"]
    assert _extract_prompt_text(parts) == "first\nsecond"


def test_extract_prompt_text_empty():
    assert _extract_prompt_text([]) == ""


def test_extract_prompt_text_ignores_non_text():
    parts = [{"type": "image", "data": "..."}, {"type": "text", "text": "ok"}]
    assert _extract_prompt_text(parts) == "ok"


# ── _extract_text_delta ──────────────────────────────────────────────────────


def test_delta_from_content_block_delta():
    line = json.dumps(
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Hello world"},
        }
    )
    assert _extract_text_delta(line) == "Hello world"


def test_delta_skips_metadata_events():
    for etype in (
        "message_start",
        "message_stop",
        "message_delta",
        "content_block_start",
        "content_block_stop",
        "result",
        "system",
    ):
        line = json.dumps({"type": etype, "data": "..."})
        assert _extract_text_delta(line) == "", f"should skip {etype}"


def test_delta_raw_text_fallback():
    assert _extract_text_delta("plain text line") == "plain text line"


def test_delta_unknown_event_with_text_field():
    line = json.dumps({"type": "custom_chunk", "text": "hi"})
    assert _extract_text_delta(line) == "hi"


def test_delta_unknown_event_without_text():
    line = json.dumps({"type": "ping", "ts": 123})
    assert _extract_text_delta(line) == ""


def test_delta_content_block_delta_non_text():
    """A tool_use delta should not emit text."""
    line = json.dumps(
        {
            "type": "content_block_delta",
            "delta": {"type": "input_json_delta", "partial_json": '{"x":1}'},
        }
    )
    assert _extract_text_delta(line) == ""


def test_delta_unwraps_stream_event_envelope():
    """`--include-partial-messages` nests the real event under `stream_event`."""
    line = json.dumps(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "pong"},
            },
        }
    )
    assert _extract_text_delta(line) == "pong"


def test_delta_ignores_stream_event_metadata():
    line = json.dumps({"type": "stream_event", "event": {"type": "message_stop"}})
    assert _extract_text_delta(line) == ""


def test_delta_skips_assistant_envelope():
    """`assistant` carries whole messages; it must not go down the delta path.

    Otherwise it would double the text whenever partial messages are on.
    """
    line = json.dumps(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}
    )
    assert _extract_text_delta(line) == ""


# ── _extract_assistant_text ──────────────────────────────────────────────────


def test_assistant_text_from_message_content():
    line = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Hello "},
                    {"type": "text", "text": "world"},
                ]
            },
        }
    )
    assert _extract_assistant_text(line) == "Hello world"


def test_assistant_text_ignores_tool_use_blocks():
    line = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {}},
                    {"type": "text", "text": "done"},
                ]
            },
        }
    )
    assert _extract_assistant_text(line) == "done"


@pytest.mark.parametrize(
    "line",
    [
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({"type": "assistant"}),
        json.dumps({"type": "assistant", "message": {}}),
        "not json",
    ],
)
def test_assistant_text_ignores_everything_else(line):
    assert _extract_assistant_text(line) == ""


# ── CLI invocation guards ────────────────────────────────────────────────────


def test_cli_env_strips_api_key_so_the_subscription_login_wins(monkeypatch):
    """An inherited API key silently outranks the claude.ai login.

    The CLI warns that connectors are disabled and billing moves to the API,
    which is not what this bridge is for.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")
    monkeypatch.setenv("PATH_MARKER", "kept")

    env = _cli_env()
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert env["PATH_MARKER"] == "kept"


def test_partial_rejection_detected_only_for_that_flag():
    assert _rejects_partial_messages(
        "error: unknown option '--include-partial-messages'"
    )
    assert not _rejects_partial_messages("error: unknown option '--wat'")
    assert not _rejects_partial_messages("")
    # A run that merely mentions the flag isn't a rejection.
    assert not _rejects_partial_messages("using --include-partial-messages")


def test_bridge_starts_out_requesting_partial_messages():
    assert ClaudeACPBridge()._partial is True


# ── _try_capture_conversation_id ─────────────────────────────────────────────


def test_capture_session_id():
    session = _Session("acp-1", "/tmp")
    line = json.dumps({"type": "result", "session_id": "conv-abc", "cost_usd": 0.003})
    _try_capture_conversation_id(session, line)
    assert session.claude_conversation_id == "conv-abc"


def test_capture_conversation_id_field():
    session = _Session("acp-1", "/tmp")
    line = json.dumps({"type": "result", "conversation_id": "conv-xyz"})
    _try_capture_conversation_id(session, line)
    assert session.claude_conversation_id == "conv-xyz"


def test_capture_ignores_non_json():
    session = _Session("acp-1", "/tmp")
    _try_capture_conversation_id(session, "not json")
    assert session.claude_conversation_id is None


def test_capture_ignores_missing_id():
    session = _Session("acp-1", "/tmp")
    _try_capture_conversation_id(session, json.dumps({"type": "result"}))
    assert session.claude_conversation_id is None


# ── ClaudeACPBridge plumbing ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_initialize_response():
    """The bridge must respond with protocolVersion and agentInfo."""
    bridge = ClaudeACPBridge()
    written: list[dict] = []

    async def capture(payload):
        written.append(payload)

    bridge._write = capture  # type: ignore[assignment]

    await bridge.handle_initialize(1, {})
    assert len(written) == 1
    result = written[0]["result"]
    assert result["protocolVersion"] == 1
    assert result["agentInfo"]["name"] == "Claude Code (CLI Bridge)"
    assert result["agentCapabilities"]["loadSession"] is False


@pytest.mark.asyncio
async def test_session_new_returns_id():
    bridge = ClaudeACPBridge()
    written: list[dict] = []

    async def capture(payload):
        written.append(payload)

    bridge._write = capture  # type: ignore[assignment]

    await bridge.handle_session_new(2, {"cwd": "/tmp"})
    assert len(written) == 1
    sid = written[0]["result"]["sessionId"]
    assert isinstance(sid, str) and len(sid) > 0
    assert sid in bridge._sessions
    assert bridge._sessions[sid].cwd == "/tmp"


@pytest.mark.asyncio
async def test_prompt_unknown_session():
    bridge = ClaudeACPBridge()
    written: list[dict] = []

    async def capture(payload):
        written.append(payload)

    bridge._write = capture  # type: ignore[assignment]

    await bridge.handle_session_prompt(
        3, {"sessionId": "nonexistent", "prompt": [{"type": "text", "text": "hi"}]}
    )
    assert len(written) == 1
    assert "error" in written[0]
    assert "Unknown session" in written[0]["error"]["message"]


@pytest.mark.asyncio
async def test_prompt_empty_text():
    bridge = ClaudeACPBridge()
    written: list[dict] = []

    async def capture(payload):
        written.append(payload)

    bridge._write = capture  # type: ignore[assignment]

    session = _Session("s-1", "/tmp")
    bridge._sessions["s-1"] = session

    await bridge.handle_session_prompt(
        4, {"sessionId": "s-1", "prompt": [{"type": "text", "text": "   "}]}
    )
    assert len(written) == 1
    assert "error" in written[0]
    assert "Empty prompt" in written[0]["error"]["message"]


@pytest.mark.asyncio
async def test_cancel_sets_flag():
    bridge = ClaudeACPBridge()
    session = _Session("s-1", "/tmp")
    bridge._sessions["s-1"] = session
    assert session.cancelled is False

    await bridge.handle_session_cancel({"sessionId": "s-1"})
    assert session.cancelled is True


@pytest.mark.asyncio
async def test_cancel_unknown_session_is_noop():
    """Cancelling a session that doesn't exist should not raise."""
    bridge = ClaudeACPBridge()
    await bridge.handle_session_cancel({"sessionId": "ghost"})


# ── _run_claude: the child process contract ──────────────────────────────────


class _FakeProc:
    """A stand-in for the ``claude -p`` child process."""

    def __init__(self, stdout_lines, stderr=b"", returncode=0):
        self.stdout = asyncio.StreamReader()
        for line in stdout_lines:
            self.stdout.feed_data(line.encode("utf-8") + b"\n")
        self.stdout.feed_eof()
        self.stderr = asyncio.StreamReader()
        self.stderr.feed_data(stderr)
        self.stderr.feed_eof()
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    async def wait(self):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


def _spawns(proc, monkeypatch):
    async def fake_exec(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)


async def _run(bridge, proc, monkeypatch):
    _spawns(proc, monkeypatch)
    monkeypatch.setattr(bridge, "_write", AsyncMock())
    return await asyncio.wait_for(
        bridge._run_claude(_Session("s-1", "/tmp"), "hi", partial=True), timeout=5.0
    )


@pytest.mark.asyncio
async def test_a_noisy_line_does_not_suppress_the_assistant_reply(monkeypatch):
    """A non-JSON line is relayed, but the real reply must still arrive.

    Node prints deprecation warnings on stdout.  Counting one as a streamed
    delta used to disable the ``assistant`` fallback for the whole turn,
    leaving the warning as the entire answer.
    """
    assistant = json.dumps(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "42"}]}}
    )
    proc = _FakeProc(["(node:9) Warning: punycode is deprecated", assistant])

    result = await _run(ClaudeACPBridge(), proc, monkeypatch)

    assert result is not None
    assert "42" in result.text


@pytest.mark.asyncio
async def test_stderr_is_read_while_the_child_is_still_running(monkeypatch):
    """The child must not be waited on before its stderr is drained.

    stderr is a pipe with a finite buffer: a chatty run fills it and blocks
    on its next write.  This fake reproduces that by refusing to exit until
    something reads stderr, so the old wait-then-drain order hangs.
    """

    class _BlockedProc(_FakeProc):
        def __init__(self):
            super().__init__(["hello"])
            self._read = asyncio.Event()
            self.stderr = _GatedStderr(self._read)

        async def wait(self):
            await self._read.wait()
            return 0

    class _GatedStderr:
        def __init__(self, read_event):
            self._read_event = read_event

        async def read(self, _n=-1):
            self._read_event.set()
            return b"npm notice"

    result = await _run(ClaudeACPBridge(), _BlockedProc(), monkeypatch)

    assert result is not None
    assert result.stderr == "npm notice"


@pytest.mark.asyncio
async def test_cancel_only_kills_its_own_session(monkeypatch):
    """Two sessions can have turns in flight; cancel must not cross over."""
    bridge = ClaudeACPBridge()
    mine, theirs = _Session("s-1", "/tmp"), _Session("s-2", "/tmp")
    mine.proc, theirs.proc = _FakeProc([]), _FakeProc([])
    mine.proc.returncode = theirs.proc.returncode = None
    bridge._sessions.update({"s-1": mine, "s-2": theirs})

    await bridge.handle_session_cancel({"sessionId": "s-1"})

    assert mine.cancelled is True and mine.proc.terminated is True
    assert theirs.cancelled is False and theirs.proc.terminated is False
