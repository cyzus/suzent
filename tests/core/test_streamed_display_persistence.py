"""Compacting model context must not rewrite the observed conversation."""

from types import SimpleNamespace
from datetime import datetime

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from suzent.core.chat_processor import ChatProcessor
from suzent.core.context_compressor import build_summary_pair
from suzent.core.display_log import merge_streamed_message
from suzent.core.display_log import recover_logged_run_timing
from suzent.streaming import _DraftDisplayAccumulator


def test_legacy_run_timing_uses_first_final_append_without_mutating_history() -> None:
    message = {
        "role": "assistant",
        "_streaming_run_id": "legacy",
        "timestamp": "2026-10-24T22:04:02.198222+01:00",
    }
    events = [
        {
            "type": "message.append",
            "ts": "2026-10-24T21:04:04Z",
            "data": {**message, "_streaming_draft": True},
        },
        {
            "type": "message.append",
            "ts": "2026-10-24T21:05:19.559799Z",
            "data": message,
        },
        {"type": "message.append", "ts": "2026-10-24T22:00:00Z", "data": message},
    ]
    recovered = recover_logged_run_timing([message], events)[0]
    assert recovered["run_finished_at"] == "2026-10-24T21:05:19.559799Z"
    assert recovered["run_timing_source"] == "log_append"
    assert "run_finished_at" not in message
    assert recover_logged_run_timing([recovered], events) == [recovered]


def test_legacy_continuation_recovers_first_splice_not_later_edit() -> None:
    message = {
        "role": "assistant",
        "_streaming_run_id": "resume",
        "timestamp": "2026-10-24T21:56:44Z",
    }
    events = [
        {
            "type": "messages.splice",
            "ts": "2026-10-24T21:56:50Z",
            "data": {"insert": [message]},
        },
        {
            "type": "messages.splice",
            "ts": "2026-10-25T10:00:00Z",
            "data": {"insert": [message]},
        },
    ]
    assert (
        recover_logged_run_timing([message], events)[0]["run_finished_at"]
        == "2026-10-24T21:56:50Z"
    )


@pytest.mark.parametrize(
    "start", ["invalid", "2026-10-25T00:00:00Z", "2026-10-24T20:00:00"]
)
def test_legacy_run_timing_rejects_unreliable_timestamps(start: str) -> None:
    message = {"role": "assistant", "_streaming_run_id": "legacy", "timestamp": start}
    events = [{"type": "message.append", "ts": "2026-10-24T21:05:19Z", "data": message}]
    assert recover_logged_run_timing([message], events) == [message]


async def test_chat_response_recovers_legacy_timing_without_rewriting_database(
    database, monkeypatch
) -> None:
    import json
    from suzent.routes import chat_routes

    chat_id = database.create_chat(title="legacy", config={})
    message = {
        "role": "assistant",
        "content": "done",
        "_streaming_run_id": "legacy",
        "timestamp": "2000-01-01T00:00:00Z",
    }
    database.update_chat(chat_id, messages=[message])
    monkeypatch.setattr(chat_routes, "get_database", lambda: database)
    monkeypatch.setattr(chat_routes, "is_background_streaming", lambda _: False)
    monkeypatch.setattr("suzent.core.retry.load_retry_checkpoint", lambda _: None)
    response = await chat_routes.get_chat(
        SimpleNamespace(path_params={"chat_id": chat_id}), include_runtime=False
    )
    assert response.status_code == 200
    recovered = json.loads(response.body)["messages"][0]
    assert recovered["run_started_at"] == message["timestamp"]
    assert recovered["run_finished_at"]
    assert recovered["run_timing_source"] == "log_append"
    assert database.get_chat(chat_id).messages == [message]


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


@pytest.mark.parametrize("target", ["inline", "canvas"])
async def test_surface_events_survive_real_stream_and_reload(
    database, target: str
) -> None:
    import asyncio
    from pydantic_ai import Agent
    from pydantic_ai.models.function import FunctionModel
    from suzent.core.agent_deps import AgentDeps
    from suzent.streaming import stream_agent_responses

    async def respond(messages, info):
        yield "Finished"

    deps = AgentDeps(a2ui_queue=asyncio.Queue())
    for revision in (1, 2):
        await deps.a2ui_queue.put(
            {
                "event": "a2ui.render",
                "id": "persistent",
                "target": target,
                "rev": revision,
                "component": {"type": "text", "content": str(revision)},
            }
        )
    await deps.a2ui_queue.put(
        {
            "event": "a2ui.render",
            "id": "question",
            "target": "inline",
            "deferred": True,
            "component": {"type": "text", "content": "Question"},
        }
    )
    agent = Agent(FunctionModel(stream_function=respond), deps_type=AgentDeps)
    chunks = [
        chunk
        async for chunk in stream_agent_responses(
            agent, "render", deps, run_id="surface-run"
        )
    ]
    assert any("a2ui.render" in chunk for chunk in chunks)
    chat_id = database.create_chat(title="surface", config={})
    assert await ChatProcessor()._persist_state(
        chat_id,
        [],
        None,
        [],
        "render",
        "Finished",
        display_run_id="surface-run",
        streamed_message=deps.streamed_message,
    )
    database.reconcile_chat_logs()
    parts = database.get_chat(chat_id).messages[-1]["parts"]
    surfaces = [part["surface"] for part in parts if part["type"] == "a2ui"]
    assert len(surfaces) == 1
    assert surfaces[0]["id"] == "persistent"
    assert surfaces[0]["target"] == target
    assert surfaces[0]["rev"] == 2


async def test_completed_run_timing_survives_persistence(database) -> None:
    chat_id = database.create_chat(title="timed", config={})
    accumulator = _DraftDisplayAccumulator(chat_id, "timed-run")
    accumulator.timestamp = "2026-10-24T10:00:00+00:00"
    accumulator.parts = [{"type": "text", "text": "done"}]
    assert "run_finished_at" not in accumulator.snapshot()
    message = accumulator.snapshot(finished_at="2026-10-24T10:01:05+00:00")
    processor = ChatProcessor()
    assert await processor._persist_state(
        chat_id,
        [],
        None,
        [],
        "task",
        "done",
        display_run_id="timed-run",
        streamed_message=message,
    )
    database.reconcile_chat_logs()
    saved = database.get_chat(chat_id).messages[-1]
    assert saved["run_started_at"] == "2026-10-24T10:00:00+00:00"
    assert saved["run_finished_at"] == "2026-10-24T10:01:05+00:00"


async def test_multiple_runs_keep_individual_timing_after_reload(database) -> None:
    chat_id = database.create_chat(title="multi-turn", config={})
    processor = ChatProcessor()
    for run_id, start, end in [
        ("first", "10:00:00", "10:00:30"),
        ("second", "10:10:30", "10:10:50"),
    ]:
        accumulator = _DraftDisplayAccumulator(chat_id, run_id)
        accumulator.timestamp = f"2026-10-24T{start}+00:00"
        accumulator.parts = [{"type": "text", "text": run_id}]
        message = accumulator.snapshot(finished_at=f"2026-10-24T{end}+00:00")
        for _ in range(2):
            assert await processor._persist_state(
                chat_id,
                [],
                None,
                [],
                "task",
                run_id,
                display_run_id=run_id,
                streamed_message=message,
            )
    database.reconcile_chat_logs()
    messages = database.get_chat(chat_id).messages
    assert [row["_streaming_run_id"] for row in messages] == ["first", "second"]
    assert (
        sum(
            (
                datetime.fromisoformat(row["run_finished_at"])
                - datetime.fromisoformat(row["run_started_at"])
            ).total_seconds()
            for row in messages
        )
        == 50
    )


@pytest.mark.parametrize("times_out", [False, True])
async def test_real_stream_keeps_tools_across_context_rewrite(monkeypatch, times_out):
    import asyncio
    from suzent import streaming

    monkeypatch.setattr(
        streaming, "_stream_idle_timeout", lambda _: 0.02 if times_out else 1.0
    )
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
    assert deps.last_messages[-1].metadata["suzent_display_run_id"] == "native-run"
    from suzent.core.fork import _agent_state_at_display_point
    from suzent.core.agent_serializer import serialize_state, deserialize_state

    forked = deserialize_state(
        _agent_state_at_display_point(
            serialize_state(deps.last_messages), [deps.streamed_message], 1
        )
    )
    assert len(forked["message_history"]) == len(deps.last_messages)
    assert requests == 2
    assert any("RUN_ERROR" in chunk for chunk in chunks) is times_out
    assert "Old answer" not in str(deps.last_messages)
    assert deps.streamed_message["_streaming_run_id"] == "native-run"
    started = datetime.fromisoformat(deps.streamed_message["run_started_at"])
    finished = datetime.fromisoformat(deps.streamed_message["run_finished_at"])
    assert started.tzinfo is not None
    assert finished >= started
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


def test_tool_only_resume_preserves_both_run_durations() -> None:
    previous = {
        "role": "assistant",
        "_streaming_run_id": "first",
        "run_started_at": "2026-10-24T10:00:00Z",
        "run_finished_at": "2026-10-24T10:00:30Z",
        "parts": [
            {"type": "tool", "toolCallId": "approval", "state": "approval-requested"}
        ],
    }
    resumed = {
        "role": "assistant",
        "_streaming_run_id": "second",
        "_resumed_tool_call_ids": ["approval"],
        "run_started_at": "2026-10-24T10:10:30Z",
        "run_finished_at": "2026-10-24T10:10:50Z",
        "parts": [{"type": "tool", "toolCallId": "approval", "state": "completed"}],
    }
    saved = merge_streamed_message([previous], resumed)
    assert len(saved) == 1
    assert [run["run_id"] for run in saved[0]["run_timings"]] == ["first", "second"]
    assert merge_streamed_message(saved, resumed) == saved
    assert "run_timings" not in previous
