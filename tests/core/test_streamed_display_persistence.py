"""Compacting model context must not rewrite the observed conversation."""

from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from suzent.core.chat_processor import ChatProcessor
from suzent.core.context_compressor import build_summary_pair
from suzent.core.display_log import merge_streamed_message
from suzent.streaming import _DraftDisplayAccumulator


@pytest.fixture
def database(tmp_path, monkeypatch):
    from suzent.database import ChatDatabase

    db = ChatDatabase(str(tmp_path / "chat.db"))
    monkeypatch.setattr("suzent.core.chat_processor.get_database", lambda: db)
    yield db
    db.engine.dispose()


def captured_run():
    accumulator = _DraftDisplayAccumulator("chat", "run-current")
    for event in [
        SimpleNamespace(
            type="TEXT_MESSAGE_CONTENT", message_id="progress", delta="Working"
        ),
        SimpleNamespace(
            type="TOOL_CALL_START", tool_call_id="tool-1", tool_call_name="read_file"
        ),
        SimpleNamespace(
            type="TOOL_CALL_ARGS", tool_call_id="tool-1", delta='{"path":"a"}'
        ),
        SimpleNamespace(
            type="TOOL_CALL_RESULT", tool_call_id="tool-1", content="file contents"
        ),
        SimpleNamespace(
            type="TEXT_MESSAGE_CONTENT", message_id="answer", delta="Current answer"
        ),
    ]:
        accumulator.apply(event)
    return accumulator.snapshot("test-model")


@pytest.mark.parametrize("empty_output", [False, True])
async def test_compacted_history_cannot_replace_the_current_run(database, empty_output):
    chat_id = database.create_chat(title="t", config={})
    old = [
        {"role": "user", "content": "continue", "_client_message_id": "first"},
        {"role": "assistant", "content": "Old answer"},
        {"role": "user", "content": "continue", "_client_message_id": "second"},
    ]
    database.update_chat(chat_id, messages=old)
    message = None if empty_output else captured_run()
    # Both the active prompt and the earlier tools are absent in model context.
    history = [ModelRequest(parts=[UserPromptPart(content="old task")])]
    history += build_summary_pair("Archived context", history)
    history += [ModelResponse(parts=[TextPart(content="Old answer")])]
    processor = ChatProcessor()
    revision = await processor._persist_agent_state_snapshot(
        chat_id, history, "test-model", [], streamed_message=message
    )
    for _ in range(2):
        assert await processor._persist_state(
            chat_id,
            history,
            "test-model",
            [],
            "continue",
            "",
            display_run_id="run-current",
            streamed_message=message,
            expected_revision=revision,
        )
    saved = database.get_chat(chat_id).messages
    assert saved[:3] == old
    assert saved[3:] == ([] if empty_output else [message])
    # Check the source-of-truth log, not just the SQLite projection.
    from suzent.database.chat_log import visible_messages

    assert visible_messages(saved) == saved
    assert database.chat_log.fold(chat_id)[0]["messages"] == saved
    database.reconcile_chat_logs()
    assert database.get_chat(chat_id).messages == saved


def test_run_identity_preserves_later_messages_and_rejects_late_drafts():
    message = captured_run()
    draft = {**message, "content": "partial", "_streaming_draft": True}
    following = {"role": "user", "content": "continue"}
    saved = merge_streamed_message([draft, following], message)
    assert saved == [message, following]
    assert merge_streamed_message(saved, draft) == saved
    assert merge_streamed_message(saved, message) == saved


def test_snapshot_is_detached_from_mutable_stream_parts():
    accumulator = _DraftDisplayAccumulator("chat", "run")
    accumulator.parts = [{"type": "tool", "displayData": {"value": "before"}}]
    message = accumulator.snapshot()
    accumulator.parts[0]["displayData"]["value"] = "after"
    assert message["parts"][0]["displayData"]["value"] == "before"


@pytest.mark.parametrize("times_out", [False, True])
async def test_real_stream_keeps_tools_across_context_rewrite(monkeypatch, times_out):
    import asyncio
    from suzent import streaming

    monkeypatch.setattr(streaming, "_stream_idle_timeout", lambda _: 0.02)
    from pydantic_ai import Agent, RunContext
    from pydantic_ai.capabilities import ProcessHistory
    from pydantic_ai.models.function import FunctionModel, DeltaToolCall
    from suzent.core.agent_deps import AgentDeps
    from suzent.streaming import stream_agent_responses

    requests = 0

    async def rewrite(ctx: RunContext[AgentDeps], messages: list) -> list:
        nonlocal requests
        requests += 1
        if requests > 1:
            messages = messages[-2:]
        ctx.deps.model_request_history = list(messages)
        return messages

    async def respond(messages, info):
        if requests == 1:
            yield {
                0: DeltaToolCall(name="lookup", json_args="{}", tool_call_id="lookup-1")
            }
        elif times_out:
            await asyncio.Event().wait()
        else:
            yield "Completed"

    agent = Agent(
        FunctionModel(stream_function=respond),
        deps_type=AgentDeps,
        capabilities=[ProcessHistory(rewrite)],
    )

    @agent.tool_plain
    def lookup() -> str:
        return "durable tool result"

    deps = AgentDeps()
    chunks = [
        chunk
        async for chunk in stream_agent_responses(
            agent,
            "continue",
            deps,
            message_history=[
                ModelRequest(parts=[UserPromptPart(content="old")]),
                ModelResponse(parts=[TextPart(content="Old answer")]),
            ],
            run_id="native-run",
        )
    ]
    assert requests == 2
    assert any("RUN_ERROR" in chunk for chunk in chunks) is times_out
    assert "Old answer" not in str(deps.last_messages)
    assert deps.streamed_message["_streaming_run_id"] == "native-run"
    assert deps.streamed_message["content"] == ("" if times_out else "Completed")
    tools = [p for p in deps.streamed_message["parts"] if p["type"] == "tool"]
    assert len(tools) == 1
    assert tools[0]["output"] == "durable tool result"
    assert tools[0]["state"] == "completed"


def test_resumed_approval_updates_original_tool_card_without_duplicate():
    previous = {
        "role": "assistant",
        "_streaming_run_id": "approval-run",
        "parts": [
            {
                "type": "tool",
                "toolCallId": "approved-call",
                "toolName": "run_command",
                "args": '{"content":"pwd"}',
                "state": "approval-requested",
                "approvalId": "approved-call",
            }
        ],
    }
    resumed = {
        "role": "assistant",
        "content": "Done",
        "_streaming_run_id": "resume-run",
        "_resumed_tool_call_ids": ["approved-call"],
        "parts": [
            {
                "type": "tool",
                "toolCallId": "approved-call",
                "toolName": "unknown",
                "args": "",
                "state": "completed",
                "approvalId": None,
                "output": "/tmp",
            },
            {"type": "text", "text": "Done"},
        ],
    }
    saved = merge_streamed_message([previous], resumed)
    assert previous["parts"][0]["state"] == "approval-requested"
    assert saved[0]["parts"][0]["state"] == "completed"
    assert saved[0]["parts"][0]["args"] == '{"content":"pwd"}'
    assert saved[0]["parts"][0]["toolName"] == "run_command"
    assert saved[1]["parts"] == [{"type": "text", "text": "Done"}]
    assert merge_streamed_message(saved, resumed) == saved
