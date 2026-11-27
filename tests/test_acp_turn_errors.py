"""How a turn reports agent-side failures and recovers from a stale session."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from suzent.acp.runtime import (
    _build_acp_file_context,
    stream_acp_steer,
    stream_acp_turn,
)


def _events(chunks):
    out = []
    for chunk in chunks:
        if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
            out.append(json.loads(chunk[6:].strip()))
    return out


def _managed(session_id="s-1", *, restored=False):
    managed = MagicMock()
    managed.agent_id = "claude-code"
    managed.session_id = session_id
    managed.cwd = "/tmp"
    managed.resumed = True
    managed.restored = restored
    managed.updates = asyncio.Queue()
    return managed


def _turn_error(text="claude cli error:"):
    return {
        "sessionId": "s-1",
        "status": "turn_error",
        "phase": "error",
        "message": text,
        "update": {"sessionUpdate": "agent_thought_chunk"},
    }


def _text_chunk(text):
    return {
        "sessionId": "s-1",
        "update": {
            "sessionUpdate": "agent_message_chunk",
            "content": {"type": "text", "text": text},
        },
    }


async def _run(managed_sequence, prompt_results, *, config=None):
    """Drive stream_acp_turn with scripted sessions and prompt outcomes."""
    sessions = list(managed_sequence)
    results = list(prompt_results)

    def attach(managed):
        async def prompt(session_id, message, on_sent=None):
            updates, result = results.pop(0)
            for item in updates:
                managed.updates.put_nowait(item)
            return result

        managed.client.prompt = prompt
        return managed

    for item in sessions:
        attach(item)

    with (
        patch("suzent.acp.runtime.get_database") as get_db,
        patch("suzent.acp.runtime.get_acp_manager") as get_manager,
    ):
        chat = MagicMock()
        chat.config = config or {
            "runtime": "acp",
            "acp_agent_id": "claude-code",
            "acp_session_id": "s-1",
        }
        chat.messages = []
        db = MagicMock()
        db.get_chat.return_value = chat
        get_db.return_value = db

        manager = AsyncMock()
        manager.ensure.return_value = sessions[0]
        manager.create.side_effect = lambda *a, **k: sessions[1]
        get_manager.return_value = manager

        events = _events([c async for c in stream_acp_turn("chat-1", "hi")])
        return events, manager, db


@pytest.mark.asyncio
async def test_agent_error_is_reported_instead_of_no_output():
    """stopReason=error must surface the agent's reason, not a generic message."""
    events, _, _ = await _run(
        [_managed()],
        [([_turn_error("claude cli error: quota exhausted")], {"stopReason": "error"})],
    )
    errors = [e for e in events if e["type"] == "RUN_ERROR"]
    assert len(errors) == 1
    assert "quota exhausted" in errors[0]["message"]
    assert "produced no output text" not in errors[0]["message"]


@pytest.mark.asyncio
async def test_unhelpful_stop_reason_is_still_named():
    events, _, _ = await _run([_managed()], [([], {"stopReason": "refusal"})])
    error = next(e for e in events if e["type"] == "RUN_ERROR")
    assert "refusal" in error["message"]


@pytest.mark.asyncio
async def test_plain_empty_turn_keeps_the_generic_message():
    events, _, _ = await _run([_managed()], [([], {"stopReason": "end_turn"})])
    error = next(e for e in events if e["type"] == "RUN_ERROR")
    assert error["message"] == "ACP agent produced no output text"


@pytest.mark.asyncio
async def test_a_cancelled_empty_turn_is_tagged_as_a_stop():
    """A stop before the first token must not look like a failure.

    The client tears the stream down on an untagged RUN_ERROR, which loses the
    turn's own ending; the tag is what tells it to keep listening.
    """
    events, _, _ = await _run([_managed()], [([], {"stopReason": "cancelled"})])
    error = next(e for e in events if e["type"] == "RUN_ERROR")
    assert error["code"] == "stream_stopped"


@pytest.mark.asyncio
async def test_stale_restored_session_recovers_on_a_fresh_one():
    """An agent that accepts a dead session id must not brick the chat."""
    first = _managed("s-1", restored=True)
    second = _managed("s-2")
    events, manager, db = await _run(
        [first, second],
        [
            ([_turn_error()], {"stopReason": "error"}),
            ([_text_chunk("THREE")], {"stopReason": "end_turn"}),
        ],
    )

    assert manager.create.await_count == 1
    resets = [e for e in events if e.get("name") == "acp.session_reset"]
    assert [r["value"]["reason"] for r in resets] == ["stale_session"]
    assert resets[0]["value"]["requestedSessionId"] == "s-1"
    assert resets[0]["value"]["sessionId"] == "s-2"

    deltas = "".join(e["delta"] for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")
    assert deltas == "THREE"
    assert not [e for e in events if e["type"] == "RUN_ERROR"]
    # The working session id must replace the stale one.
    assert any(
        call.args[1].get("acp_session_id") == "s-2"
        for call in db.merge_chat_config.call_args_list
    )


@pytest.mark.asyncio
async def test_a_live_session_failure_does_not_start_a_new_session():
    """Only a freshly restored session earns a retry; a proven one just errors."""
    events, manager, _ = await _run(
        [_managed("s-1", restored=False)],
        [([_turn_error("transient")], {"stopReason": "error"})],
    )
    assert manager.create.await_count == 0
    assert any(e["type"] == "RUN_ERROR" for e in events)
    assert not [e for e in events if e.get("name") == "acp.session_reset"]


@pytest.mark.asyncio
async def test_successful_turn_clears_the_restored_flag():
    managed = _managed("s-1", restored=True)
    await _run([managed], [([_text_chunk("ok")], {"stopReason": "end_turn"})])
    assert managed.restored is False


# ── file context ──────────────────────────────────────────────────────────────


def test_build_acp_file_context_from_mentions():
    ctx = _build_acp_file_context(
        file_mentions=[
            {"path": "/tmp/a.py", "type": "file"},
            {"path": "/tmp/src", "type": "directory"},
        ]
    )
    assert "[User referenced file: /tmp/a.py]" in ctx
    assert "[User referenced directory: /tmp/src]" in ctx


def test_build_acp_file_context_empty_when_no_mentions():
    assert _build_acp_file_context() == ""
    assert _build_acp_file_context(file_mentions=[]) == ""


def test_build_acp_file_context_plain_strings():
    ctx = _build_acp_file_context(file_mentions=["/tmp/x.txt"])
    assert "[User referenced file: /tmp/x.txt]" in ctx


# ── steer ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_steer_cancels_then_reprompts():
    """stream_acp_steer must cancel the current prompt, then send a new turn."""
    managed = _managed()

    with (
        patch("suzent.acp.runtime.get_database") as get_db,
        patch("suzent.acp.runtime.get_acp_manager") as get_mgr,
    ):
        chat = MagicMock()
        chat.config = {
            "runtime": "acp",
            "acp_agent_id": "claude-code",
            "acp_session_id": "s-1",
        }
        chat.messages = []
        db = MagicMock()
        db.get_chat.return_value = chat
        get_db.return_value = db

        manager = AsyncMock()
        manager.ensure.return_value = managed
        get_mgr.return_value = manager

        async def prompt(session_id, message, on_sent=None):
            managed.updates.put_nowait(_text_chunk("steered"))
            return {"stopReason": "end_turn"}

        managed.client.prompt = prompt

        events = _events([c async for c in stream_acp_steer("chat-1", "use rust")])

    manager.cancel.assert_awaited_once_with("chat-1")
    deltas = "".join(e["delta"] for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")
    assert deltas == "steered"


@pytest.mark.asyncio
async def test_file_mentions_injected_into_acp_prompt():
    """File mentions must appear in the message the ACP agent receives."""
    managed = _managed()
    captured_messages: list[str] = []

    with (
        patch("suzent.acp.runtime.get_database") as get_db,
        patch("suzent.acp.runtime.get_acp_manager") as get_mgr,
    ):
        chat = MagicMock()
        chat.config = {
            "runtime": "acp",
            "acp_agent_id": "claude-code",
            "acp_session_id": "s-1",
        }
        chat.messages = []
        db = MagicMock()
        db.get_chat.return_value = chat
        get_db.return_value = db

        manager = AsyncMock()
        manager.ensure.return_value = managed
        get_mgr.return_value = manager

        async def prompt(session_id, message, on_sent=None):
            captured_messages.append(message)
            managed.updates.put_nowait(_text_chunk("ok"))
            return {"stopReason": "end_turn"}

        managed.client.prompt = prompt

        events = _events(
            [
                c
                async for c in stream_acp_turn(
                    "chat-1",
                    "read this",
                    file_mentions=[{"path": "/tmp/data.csv", "type": "file"}],
                )
            ]
        )

    assert len(captured_messages) == 1
    assert "/tmp/data.csv" in captured_messages[0]
    assert "read this" in captured_messages[0]
    assert not [e for e in events if e["type"] == "RUN_ERROR"]


@pytest.mark.asyncio
async def test_binary_uploads_emit_unsupported_warning():
    """Binary file uploads must produce a warning event, not be silently dropped."""
    managed = _managed()

    with (
        patch("suzent.acp.runtime.get_database") as get_db,
        patch("suzent.acp.runtime.get_acp_manager") as get_mgr,
    ):
        chat = MagicMock()
        chat.config = {
            "runtime": "acp",
            "acp_agent_id": "claude-code",
            "acp_session_id": "s-1",
        }
        chat.messages = []
        db = MagicMock()
        db.get_chat.return_value = chat
        get_db.return_value = db

        manager = AsyncMock()
        manager.ensure.return_value = managed
        get_mgr.return_value = manager

        async def prompt(session_id, message, on_sent=None):
            managed.updates.put_nowait(_text_chunk("ok"))
            return {"stopReason": "end_turn"}

        managed.client.prompt = prompt

        events = _events(
            [
                c
                async for c in stream_acp_turn(
                    "chat-1",
                    "describe this image",
                    files=[{"name": "photo.png", "data": b"..."}],
                )
            ]
        )

    warnings = [e for e in events if e.get("name") == "acp.files_unsupported"]
    assert len(warnings) == 1
    assert warnings[0]["value"]["count"] == 1


@pytest.mark.asyncio
async def test_acp_thoughts_and_tool_calls_translate_to_agui_and_persist():
    """ACP agent_thought_chunk and tool_call updates must stream as AG-UI events and persist in parts."""
    updates = [
        {
            "sessionId": "s-1",
            "update": {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": "text", "text": "Checking skills directory..."},
            },
        },
        {
            "sessionId": "s-1",
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "tc-1",
                "kind": "read",
                "title": "Read skills/README.md",
                "status": "in_progress",
                "rawInput": {"file_path": "/workspace/skills/README.md"},
            },
        },
        {
            "sessionId": "s-1",
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "tc-1",
                "status": "completed",
                "content": [
                    {
                        "type": "content",
                        "content": {"type": "text", "text": "# Skills\n1. notebook"},
                    }
                ],
            },
        },
        _text_chunk("Here are the skills I found."),
    ]
    events, _, db = await _run(
        [_managed()],
        [(updates, {"stopReason": "end_turn"})],
    )

    types = [e["type"] for e in events]
    assert "REASONING_MESSAGE_CHUNK" in types
    assert "TOOL_CALL_START" in types
    assert "TOOL_CALL_ARGS" in types
    assert "TOOL_CALL_RESULT" in types
    assert "TEXT_MESSAGE_CONTENT" in types

    tc_start = next(e for e in events if e["type"] == "TOOL_CALL_START")
    assert tc_start["toolCallId"] == "tc-1"
    assert tc_start["toolCallName"] == "read_file"

    tc_res = next(e for e in events if e["type"] == "TOOL_CALL_RESULT")
    assert tc_res["toolCallId"] == "tc-1"
    assert "# Skills" in tc_res["content"]

    # Check persisted assistant message row includes parts (reasoning, tool, text)
    assistant_calls = [
        call.args[1]
        for call in db.append_chat_message.call_args_list
        if call.args[1].get("role") == "assistant"
    ]
    assert len(assistant_calls) == 1
    persisted = assistant_calls[0]
    assert persisted["model"] == "acp/claude-code"
    assert persisted["content"] == "Here are the skills I found."
    parts = persisted["parts"]
    assert [p["type"] for p in parts] == ["reasoning", "tool", "text"]
    assert parts[0]["text"] == "Checking skills directory..."
    assert parts[1]["toolName"] == "read_file"
    assert parts[1]["state"] == "completed"
    assert "# Skills" in parts[1]["output"]


@pytest.mark.asyncio
async def test_acp_failed_turn_after_thought_still_emits_run_error():
    """A turn that emits thoughts and then fails with stopReason=error must report RUN_ERROR."""
    updates = [
        {
            "sessionId": "s-1",
            "update": {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": "text", "text": "Thinking before quota failure..."},
            },
        },
        _turn_error("quota exhausted"),
    ]
    events, _, _ = await _run(
        [_managed()],
        [(updates, {"stopReason": "error"})],
    )
    errors = [e for e in events if e["type"] == "RUN_ERROR"]
    assert len(errors) == 1
    assert "quota exhausted" in errors[0]["message"]


@pytest.mark.asyncio
async def test_acp_tool_args_update_replaces_snapshot():
    """When tool args are refined across updates, TOOL_CALL_START is re-sent so the client replaces args."""
    updates = [
        {
            "sessionId": "s-1",
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "tc-1",
                "title": "Read file",
                "status": "pending",
            },
        },
        {
            "sessionId": "s-1",
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "tc-1",
                "kind": "read",
                "rawInput": {"file_path": "/workspace/a.txt"},
                "status": "completed",
            },
        },
        _text_chunk("Done."),
    ]
    events, _, db = await _run(
        [_managed()],
        [(updates, {"stopReason": "end_turn"})],
    )
    starts = [
        e
        for e in events
        if e["type"] == "TOOL_CALL_START" and e["toolCallId"] == "tc-1"
    ]
    assert len(starts) == 2
    assistant_calls = [
        call.args[1]
        for call in db.append_chat_message.call_args_list
        if call.args[1].get("role") == "assistant"
    ]
    tool_part = next(p for p in assistant_calls[0]["parts"] if p["type"] == "tool")
    assert json.loads(tool_part["args"]) == {"file_path": "/workspace/a.txt"}


@pytest.mark.asyncio
async def test_acp_tool_retains_in_progress_output_and_emits_failure_outcome():
    """Tool output streamed during in_progress is retained on status-only completion, and failed tools emit tool_call_outcome."""
    updates = [
        {
            "sessionId": "s-1",
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "tc-out",
                "kind": "execute",
                "rawInput": {"command": "echo hello"},
                "rawOutput": {"stdout": "hello\n"},
                "status": "in_progress",
            },
        },
        {
            "sessionId": "s-1",
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "tc-out",
                "status": "completed",
            },
        },
        {
            "sessionId": "s-1",
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "tc-fail",
                "kind": "execute",
                "rawInput": {"command": "false"},
                "rawOutput": {"exit_code": 1},
                "status": "failed",
            },
        },
        _text_chunk("Done."),
    ]
    events, _, db = await _run(
        [_managed()],
        [(updates, {"stopReason": "end_turn"})],
    )
    tc_out_results = [
        e
        for e in events
        if e["type"] == "TOOL_CALL_RESULT" and e["toolCallId"] == "tc-out"
    ]
    assert len(tc_out_results) == 1
    assert "hello" in tc_out_results[0]["content"]

    outcomes = [
        e
        for e in events
        if e["type"] == "CUSTOM" and e.get("name") == "tool_call_outcome"
    ]
    assert len(outcomes) == 1
    assert outcomes[0]["value"] == {"toolCallId": "tc-fail", "outcome": "failed"}

    assistant_calls = [
        call.args[1]
        for call in db.append_chat_message.call_args_list
        if call.args[1].get("role") == "assistant"
    ]
    tc_out_part = next(
        p for p in assistant_calls[0]["parts"] if p.get("toolCallId") == "tc-out"
    )
    assert "hello" in tc_out_part["output"]
    assert json.loads(tc_out_part["args"])["content"] == "echo hello"


@pytest.mark.asyncio
async def test_acp_tool_completion_metadata_does_not_overwrite_raw_input():
    """A completion update with only locations/title/path-only diff must not overwrite earlier rawInput args."""
    updates = [
        {
            "sessionId": "s-1",
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "tc-edit",
                "kind": "edit",
                "rawInput": {
                    "file_path": "a.txt",
                    "old_string": "foo",
                    "new_string": "bar",
                },
                "status": "in_progress",
            },
        },
        {
            "sessionId": "s-1",
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "tc-edit",
                "title": "Edit a.txt",
                "locations": [{"path": "a.txt"}],
                "content": [{"type": "diff", "path": "a.txt"}],
                "status": "completed",
            },
        },
        _text_chunk("Edited."),
    ]
    events, _, db = await _run(
        [_managed()],
        [(updates, {"stopReason": "end_turn"})],
    )
    arg_events = [
        e
        for e in events
        if e["type"] == "TOOL_CALL_ARGS" and e["toolCallId"] == "tc-edit"
    ]
    assert len(arg_events) == 1
    assert json.loads(arg_events[0]["delta"]) == {
        "file_path": "a.txt",
        "old_string": "foo",
        "new_string": "bar",
    }
    assistant_calls = [
        call.args[1]
        for call in db.append_chat_message.call_args_list
        if call.args[1].get("role") == "assistant"
    ]
    tc_edit_part = next(
        p for p in assistant_calls[0]["parts"] if p.get("toolCallId") == "tc-edit"
    )
    assert tc_edit_part["toolName"] == "edit_file"
    assert json.loads(tc_edit_part["args"]) == {
        "file_path": "a.txt",
        "old_string": "foo",
        "new_string": "bar",
    }


@pytest.mark.asyncio
async def test_acp_tool_name_update_emitted_even_when_args_unchanged():
    """When a later update refines tool kind/name without changing args, TOOL_CALL_START is emitted with the new name."""
    updates = [
        {
            "sessionId": "s-1",
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "tc-name",
                "title": "Inspecting",
                "rawInput": {"file_path": "a.txt"},
                "status": "pending",
            },
        },
        {
            "sessionId": "s-1",
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "tc-name",
                "kind": "read",
                "status": "completed",
            },
        },
        _text_chunk("Read complete."),
    ]
    events, _, _ = await _run(
        [_managed()],
        [(updates, {"stopReason": "end_turn"})],
    )
    starts = [
        e
        for e in events
        if e["type"] == "TOOL_CALL_START" and e["toolCallId"] == "tc-name"
    ]
    assert [s["toolCallName"] for s in starts] == ["Inspecting", "read_file"]


@pytest.mark.asyncio
async def test_acp_new_file_diff_supplies_empty_old_string():
    """New-file diff blocks with oldText=None must populate old_string='' so FileDiffViewer can preview."""
    updates = [
        {
            "sessionId": "s-1",
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "tc-new",
                "kind": "edit",
                "content": [
                    {
                        "type": "diff",
                        "path": "new.py",
                        "oldText": None,
                        "newText": "print('hi')\n",
                    }
                ],
                "status": "completed",
            },
        },
        _text_chunk("Created new.py."),
    ]
    _, _, db = await _run(
        [_managed()],
        [(updates, {"stopReason": "end_turn"})],
    )
    assistant_calls = [
        call.args[1]
        for call in db.append_chat_message.call_args_list
        if call.args[1].get("role") == "assistant"
    ]
    part = next(
        p for p in assistant_calls[0]["parts"] if p.get("toolCallId") == "tc-new"
    )
    assert json.loads(part["args"]) == {
        "file_path": "new.py",
        "old_string": "",
        "new_string": "print('hi')\n",
    }
