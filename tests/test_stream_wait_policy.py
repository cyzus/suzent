import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel

from suzent import streaming
from suzent.config import CONFIG
from suzent.config.model import ConfigModel
from suzent.core.providers.catalog import PROVIDER_REGISTRY_BY_ID, _parse_provider
from suzent.tools.capability import ToolResultContextCapability


def test_wait_policy_precedence_and_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(CONFIG, "stream_idle_timeout_seconds", 7)
    provider = replace(
        PROVIDER_REGISTRY_BY_ID["gemini"], stream_idle_timeout_seconds=19
    )
    monkeypatch.setitem(PROVIDER_REGISTRY_BY_ID, "gemini", provider)
    monkeypatch.setitem(PROVIDER_REGISTRY_BY_ID, "google", provider)
    monkeypatch.setattr(CONFIG, "stream_idle_timeout_overrides", {})
    assert streaming._stream_idle_timeout("gemini/model") == 19
    assert streaming._stream_idle_timeout("google/model") == 19
    assert streaming._stream_idle_timeout("custom/model") == 7
    assert streaming._stream_idle_timeout(None) == 7
    monkeypatch.setattr(CONFIG, "stream_idle_timeout_overrides", {"gemini": 23})
    assert streaming._stream_idle_timeout("google/model") == 23
    monkeypatch.setattr(
        CONFIG, "stream_idle_timeout_overrides", {"gemini": 23, "google/model": 29}
    )
    assert streaming._stream_idle_timeout("google/model") == 29


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_wait_policy_rejects_invalid_values(value: float) -> None:
    for field in [
        "stream_idle_timeout_seconds",
        "stream_wait_notice_seconds",
        "stream_wait_slow_seconds",
        "stream_wait_extension_seconds",
    ]:
        with pytest.raises(ValidationError):
            ConfigModel(**{field: value})
    with pytest.raises(ValidationError):
        ConfigModel(stream_idle_timeout_overrides={"custom": value})
    with pytest.raises(ValidationError):
        _parse_provider(
            {
                "id": "custom",
                "label": "Custom",
                "api_type": "google",
                "stream_idle_timeout_seconds": value,
            }
        )


async def test_idle_wait_uses_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(CONFIG, "stream_idle_timeout_seconds", 0.001)
    monkeypatch.setattr(CONFIG, "stream_idle_timeout_overrides", {"custom/slow": 0.2})

    class SlowAgent:
        _model_id = "custom/slow"

        @asynccontextmanager
        async def run_stream_events(self, *_args: object, **_kwargs: object):
            async def events():
                yield SimpleNamespace(event_kind="part_start")
                await asyncio.sleep(0.02)
                yield SimpleNamespace(event_kind="part_delta")

            yield events()

    events = [
        event
        async for event in streaming._iter_stream_events_with_timeout(
            SlowAgent(), "hi", {}
        )
    ]
    assert len(events) == 2


async def test_wait_notice_clears_on_resume_and_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from suzent.core import stream_registry

    monkeypatch.setattr(CONFIG, "stream_wait_notice_seconds", 0.005)
    notices = []

    async def push(chat_id: str, name: str, value: dict) -> None:
        notices.append((chat_id, name, value["active"]))

    monkeypatch.setattr(stream_registry, "push_custom_event", push)
    closed = asyncio.Event()

    async def source():
        try:
            await asyncio.sleep(0.02)
            yield "resumed"
            await asyncio.Event().wait()
        finally:
            closed.set()

    stream = source()
    assert await streaming._await_model_event(stream, 0.2, None, "chat") == "resumed"
    assert notices == [
        ("chat", "model_response_wait", True),
        ("chat", "model_response_wait", False),
    ]
    notices.clear()
    pending = asyncio.create_task(
        streaming._await_model_event(stream, 0.2, None, "chat")
    )
    while not notices:
        await asyncio.sleep(0)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert closed.is_set()
    assert notices[-1] == ("chat", "model_response_wait", False)


@pytest.mark.parametrize("live_result", [False, True])
async def test_file_snapshots_only_removed_from_model_request(
    live_result: bool,
) -> None:
    from suzent.tools.base import ToolResult

    metadata = {
        "old_content": "before" * 10000,
        "new_content": "after" * 10000,
        "replaced_count": 1,
        "abs_path": "/tmp/example",
    }
    content = {"success": True, "message": "Edited", "metadata": metadata}
    if live_result:
        content = ToolResult.success_result("Edited", metadata=metadata)
    original = ToolReturnPart(
        tool_name="edit_file", content=content, tool_call_id="edit"
    )
    seen = []

    def respond(messages: list, _info: object) -> ModelResponse:
        seen.extend(messages)
        return ModelResponse(parts=[TextPart("ok")])

    agent = Agent(FunctionModel(respond), capabilities=[ToolResultContextCapability()])
    result = await agent.run(
        "continue",
        message_history=[
            ModelResponse(
                parts=[
                    ToolCallPart(tool_name="edit_file", args={}, tool_call_id="edit")
                ]
            ),
            ModelRequest(parts=[original]),
        ],
    )
    sent = next(
        part
        for message in seen
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    )
    assert sent.content["metadata"] == {"replaced_count": 1, "abs_path": "/tmp/example"}
    assert original.content is content
    stored = result.all_messages()[1].parts[0]
    assert stored.content is content


async def test_slow_wait_only_extends_after_user_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from suzent.core import stream_registry
    from suzent.core.stream_registry import StreamControl

    monkeypatch.setattr(CONFIG, "stream_wait_notice_seconds", 0.005)
    monkeypatch.setattr(CONFIG, "stream_wait_slow_seconds", 0.01)
    monkeypatch.setattr(CONFIG, "stream_wait_extension_seconds", 0.2)
    control = StreamControl()
    stages: list[str] = []

    async def push(_chat_id: str, _name: str, value: dict) -> None:
        if value.get("active"):
            stages.append(value["stage"])
            if value["stage"] == "slow":
                assert value["can_extend"] is True
                assert control.model_wait.wait_id == value["wait_id"]
                assert control.model_wait.extend()
                assert not control.model_wait.extend()

    monkeypatch.setattr(stream_registry, "push_custom_event", push)

    async def source():
        await asyncio.sleep(0.06)
        yield "finished"

    result = await streaming._await_model_event(source(), 0.03, None, "chat", control)
    assert result == "finished"
    assert stages == ["waiting", "slow", "extended"]
    assert control.model_wait is None


async def test_slow_notice_does_not_extend_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from suzent.core import stream_registry
    from suzent.core.stream_registry import StreamControl

    monkeypatch.setattr(CONFIG, "stream_wait_notice_seconds", 0.005)
    monkeypatch.setattr(CONFIG, "stream_wait_slow_seconds", 0.01)
    monkeypatch.setattr(CONFIG, "stream_wait_extension_seconds", 0.2)
    stages = []

    async def push(_chat_id: str, _name: str, value: dict) -> None:
        stages.append(value)

    monkeypatch.setattr(stream_registry, "push_custom_event", push)
    control = StreamControl()

    async def source():
        await asyncio.Event().wait()
        yield "never"

    with pytest.raises(asyncio.TimeoutError):
        await streaming._await_model_event(source(), 0.03, None, "chat", control)
    assert [notice.get("stage") for notice in stages] == ["waiting", "slow", None]
    assert stages[-1]["active"] is False
    assert control.model_wait is None


async def test_compaction_does_not_count_against_the_idle_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mid-run compaction runs inside the wait for the next model event."""
    from suzent.core import context_compressor as cc
    from suzent.core import stream_registry

    async def push(*_args: object) -> None:
        return None

    monkeypatch.setattr(stream_registry, "push_custom_event", push)

    async def compacting_then_event():
        with cc._track_compaction("c-wait"):
            await asyncio.sleep(0.3)
        yield "after-compaction"

    event = await streaming._await_model_event(
        compacting_then_event(), 0.1, None, "c-wait"
    )
    assert event == "after-compaction"

    async def silent():
        await asyncio.sleep(0.3)
        yield "late"

    with pytest.raises(asyncio.TimeoutError):
        await streaming._await_model_event(silent(), 0.1, None, "c-wait")
