import asyncio
from contextlib import asynccontextmanager

from pydantic_ai.messages import (
    EnqueuedMessagesEvent,
    FunctionToolCallEvent,
    ModelRequest,
    ToolCallPart,
    UserPromptPart,
)

from suzent import streaming
from suzent.core.agent_inbox import AgentInboxDispatcher
from suzent.core.stream_registry import StreamControl


class _FakeRun:
    def __init__(self):
        self.enqueued = []

    def enqueue(self, content, priority="asap"):
        self.enqueued.append((content, priority))
        return f"enq-{len(self.enqueued)}"


class _FakeStream:
    """Mimics AgentRunEvents: exposes result + the private run accessor."""

    def __init__(self, run=None, result=None):
        self.result = result
        self._run = run

    def _agent_run(self):
        if self._run is None:
            raise RuntimeError("run has not started")
        return self._run


def test_injector_returns_enqueue_id():
    run = _FakeRun()
    inject = streaming._make_run_injector(_FakeStream(run))

    assert inject("hello") == "enq-1"
    assert run.enqueued == [("hello", "asap")]


def test_injector_refuses_finished_run():
    run = _FakeRun()
    inject = streaming._make_run_injector(_FakeStream(run, result=object()))

    assert inject("hello") is None
    assert run.enqueued == []


def test_injector_refuses_unstarted_run():
    inject = streaming._make_run_injector(_FakeStream(None))
    assert inject("hello") is None


class _InjectableStreamAgent:
    """Emits a tool call, then confirms an enqueued message was delivered."""

    def run_stream_events(self, _prompt, **_kwargs):
        @asynccontextmanager
        async def stream():
            async def events():
                yield FunctionToolCallEvent(
                    ToolCallPart(
                        tool_name="run_command",
                        args={"content": "pwd"},
                        tool_call_id="call-1",
                    )
                )
                yield EnqueuedMessagesEvent(
                    enqueue_id="enq-1",
                    messages=(
                        ModelRequest(parts=[UserPromptPart(content="sub-agent done")]),
                    ),
                )

            yield events()

        return stream()


async def test_stream_registers_hook_and_confirms_delivery():
    control = StreamControl()

    events = []
    async for event in streaming._iter_stream_events_with_timeout(
        _InjectableStreamAgent(), "hi", {}, control
    ):
        events.append(event.event_kind)

    assert "enqueued_messages" in events
    assert control.injection_delivered("enq-1").is_set()
    # Hook is cleared once the run is over.
    assert control.inject is None


async def test_inject_into_live_run_confirms():
    control = StreamControl()
    control.inject = lambda content: "enq-7"

    task = asyncio.create_task(
        AgentInboxDispatcher()._inject_into_live_run(
            control, "chat-1", "sub-agent done", True
        )
    )
    await asyncio.sleep(0)
    control.mark_injected("enq-7")

    assert await asyncio.wait_for(task, timeout=1) is True


async def test_inject_falls_back_when_run_ends_first():
    control = StreamControl()
    control.inject = lambda content: "enq-7"

    task = asyncio.create_task(
        AgentInboxDispatcher()._inject_into_live_run(
            control, "chat-1", "sub-agent done", True
        )
    )
    await asyncio.sleep(0)
    control.completed_event.set()  # run died before draining

    assert await asyncio.wait_for(task, timeout=1) is False


async def test_inject_falls_back_without_a_live_run():
    control = StreamControl()
    assert (
        await AgentInboxDispatcher()._inject_into_live_run(
            control, "chat-1", "sub-agent done", True
        )
        is False
    )
