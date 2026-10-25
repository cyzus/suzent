import asyncio

from suzent.voice.handoff import VOICE_TURN_REMINDER, HandoffRouter, build_delegation


def sse(payload: str) -> str:
    return f"data: {payload}\n\n"


class Harness:
    """A router wired to fakes: records what reaches the front desk and the turn."""

    def __init__(self, *, chunks=(), busy=False, inject_result="q1", hold=None):
        self.context: list[str] = []
        self.spoken: list[str] = []
        self.working: list[bool] = []
        self.turns: list[tuple[str, list[str]]] = []
        self.injected: list[str] = []
        self.stopped = 0
        self.lines: list[tuple[str, str]] = []
        self.busy = busy
        self.hold = hold
        self.chunks = list(chunks)
        self.inject_result = inject_result

        async def send_context(text):
            self.context.append(text)

        async def on_working(active):
            self.working.append(active)

        async def start_turn(message, reminders, on_chunk):
            self.turns.append((message, reminders))
            if self.hold is not None:
                await self.hold.wait()
            for chunk in self.chunks:
                await on_chunk(chunk)

        async def observe_turn(on_chunk):
            if self.hold is not None:
                await self.hold.wait()
            for chunk in self.chunks:
                await on_chunk(chunk)

        def take():
            lines, self.lines = self.lines, []
            return lines

        def inject(text):
            self.injected.append(text)
            return self.inject_result

        def stop():
            self.stopped += 1
            return True

        self.router = HandoffRouter(
            "chat",
            send_context=send_context,
            enqueue_spoken=self.spoken.append,
            on_working=on_working,
            transcript_delta=take,
            start_turn=start_turn,
            observe_turn=observe_turn,
            inject=inject,
            is_busy=lambda: self.busy,
            stop=stop,
            progress_interval=0,
            transcript_grace=0.05,
        )

    def say(self, utterance_id: str, text: str):
        self.lines.append(("user", text))
        self.router.note_user_utterance(utterance_id)


async def _settle(router):
    if router._task is not None:
        await asyncio.wait_for(router._task, 2)
    if router._observer_task is not None:
        await asyncio.wait_for(router._observer_task, 2)


async def test_delegate_returns_at_once_and_records_the_front_desks_reading():
    h = Harness(chunks=[sse('{"type":"TEXT_MESSAGE_CONTENT","delta":"晴天"}')])
    h.say("a:1", "今天伦敦天气怎么样")
    result = await h.router.delegate("Check London weather today")
    assert result.startswith("started")
    await _settle(h.router)

    message, reminders = h.turns[0]
    # The chat row is the front desk's clear reading, not the raw transcript:
    # ASR output is full of scaffolding that is never a clean user message.
    assert message == "Check London weather today"
    assert reminders[0] == VOICE_TURN_REMINDER
    assert "<input>Check London weather today</input>" in reminders[1]
    assert "user: 今天伦敦天气怎么样" in reminders[1]
    assert h.working == [True, False]
    assert len(h.spoken) == 1 and "晴天" in h.spoken[0]
    assert h.spoken[0].startswith("<system>")


async def test_delegate_falls_back_to_request_without_a_transcript():
    h = Harness()
    assert (await h.router.delegate("look this up")).startswith("started")
    await _settle(h.router)
    assert h.turns[0][0] == "look this up"


async def test_delegate_waits_briefly_for_a_late_user_transcript():
    h = Harness()
    h.router._transcript_grace = 1.0

    async def late():
        await asyncio.sleep(0.05)
        h.say("a:2", "late words")

    asyncio.create_task(late())
    await h.router.delegate("paraphrase")
    await _settle(h.router)
    assert h.turns[0][0] == "paraphrase"


async def test_repeat_delegation_for_one_utterance_starts_one_turn():
    hold = asyncio.Event()
    h = Harness(hold=hold)
    h.say("a:1", "do the thing")
    first, second = await asyncio.gather(
        h.router.delegate("do the thing"), h.router.delegate("do the thing")
    )
    assert sorted([first.split(":")[0], second.split(":")[0]]) == [
        "already_delegated",
        "started",
    ]
    assert (await h.router.delegate("do the thing")).startswith("already_delegated")
    hold.set()
    await _settle(h.router)
    assert len(h.turns) == 1


async def test_new_utterance_while_working_is_steered_into_the_turn():
    hold = asyncio.Event()
    h = Harness(hold=hold)
    h.say("a:1", "write a report")
    await h.router.delegate("write a report")
    h.say("a:2", "make it short")
    result = await h.router.delegate("make the report short")
    assert result.startswith("steered")
    assert h.injected[0].startswith("make it short")
    assert "make the report short" in h.injected[0]
    hold.set()
    await _settle(h.router)
    assert len(h.turns) == 1


async def test_new_request_whose_words_arrive_after_the_tool_call_is_steered():
    # Gemini 3.x calls `delegate` before it finalizes the user's transcript:
    # the new request must not be mistaken for a repeat of the previous one.
    hold = asyncio.Event()
    h = Harness(hold=hold)
    h.router._transcript_grace = 1.0
    h.say("a:1", "write a report")
    await h.router.delegate("write a report")

    async def late():
        await asyncio.sleep(0.05)
        h.say("a:2", "also add a chart")

    asyncio.create_task(late())
    result = await h.router.delegate("add a chart to the report")
    assert result.startswith("steered")
    assert h.injected[0].startswith("also add a chart")
    hold.set()
    await _settle(h.router)
    assert len(h.turns) == 1


async def test_repeat_without_new_words_is_caught_when_the_turn_is_not_ours():
    # The chat is busy with a turn that outlived an earlier call: a repeat
    # call must not steer the same words a second time.
    h = Harness(busy=True)
    h.say("a:1", "x")
    assert (await h.router.delegate("x")).startswith("steered")
    assert (await h.router.delegate("x")).startswith("already_delegated")
    assert h.injected == ["x"]


async def test_repeat_after_a_fast_turn_finished_does_not_start_another():
    h = Harness()
    h.say("a:1", "x")
    assert (await h.router.delegate("x")).startswith("started")
    await _settle(h.router)
    assert (await h.router.delegate("x")).startswith("already_delegated")
    # A different request without transcribed words is still taken.
    assert (await h.router.delegate("y")).startswith("started")
    await _settle(h.router)
    assert [message for message, _ in h.turns] == ["x", "y"]


async def test_busy_chat_that_cannot_take_input_says_busy():
    h = Harness(busy=True, inject_result=None)
    assert (await h.router.delegate("x")).startswith("busy")
    assert h.turns == []


async def test_request_after_a_greeting_the_front_desk_answered_starts_a_turn():
    # "你好吗？" then "今天天气如何呀？": the front desk answers the greeting
    # itself, so the greeting is still unread when the real request arrives.
    # Counting it as new words made the request a steer of a finished turn.
    h = Harness()
    h.say("a:1", "你好吗？")
    await asyncio.sleep(0)
    h.router.note_front_desk_turn_end(h.lines)

    h.say("a:2", "今天天气如何呀？")
    result = await h.router.delegate("查询今天的天气")
    assert result.startswith("started")
    assert h.injected == []
    await _settle(h.router)
    assert [message for message, _ in h.turns] == ["查询今天的天气"]


async def test_late_transcript_after_a_delegating_turn_end_is_not_swallowed():
    # Turn completion also fires for a turn that delegated, and a provider may
    # finalize the user's words after it. Those words are a new request.
    hold = asyncio.Event()
    h = Harness(hold=hold)
    h.say("a:1", "write a report")
    await h.router.delegate("write a report")
    h.router.note_front_desk_turn_end([])

    h.say("a:2", "check the weather")
    assert (await h.router.delegate("check the weather")).startswith("steered")
    hold.set()
    await _settle(h.router)
    assert h.injected[0].startswith("check the weather")


async def test_cancel_task():
    h = Harness()
    assert (await h.router.cancel_task()).startswith("nothing_running")
    h.busy = True
    assert (await h.router.cancel_task()).startswith("cancelled")
    assert h.stopped == 1


async def test_progress_failure_and_approval_reports():
    h = Harness(
        chunks=[
            sse('{"type":"TOOL_CALL_START","toolCallName":"web_search"}'),
            sse('{"type":"RUN_ERROR","message":"model down"}'),
        ]
    )
    await h.router.delegate("x")
    await _settle(h.router)
    assert any("web_search" in c for c in h.context)
    assert "model down" in h.spoken[0]

    h2 = Harness(
        chunks=[sse('{"type":"CUSTOM","name":"tool_approval_request","value":{}}')]
    )
    await h2.router.delegate("x")
    await _settle(h2.router)
    assert "approval" in h2.spoken[0]


async def test_only_the_last_message_is_the_answer():
    h = Harness(
        chunks=[
            sse('{"type":"TEXT_MESSAGE_START","messageId":"1"}'),
            sse(
                '{"type":"TEXT_MESSAGE_CONTENT","messageId":"1","delta":"let me look"}'
            ),
            sse('{"type":"TEXT_MESSAGE_START","messageId":"2"}'),
            sse('{"type":"TEXT_MESSAGE_CONTENT","messageId":"2","delta":"final"}'),
        ]
    )
    await h.router.delegate("x")
    await _settle(h.router)
    assert "final" in h.spoken[0] and "let me look" not in h.spoken[0]


async def test_turn_survives_close_and_reports_nothing():
    hold = asyncio.Event()
    h = Harness(hold=hold, chunks=[sse('{"type":"TEXT_MESSAGE_CONTENT","delta":"ok"}')])
    await h.router.delegate("x")
    task = h.router._task
    h.router.close()
    assert not task.done()
    hold.set()
    await asyncio.wait_for(task, 2)
    assert h.spoken == []


async def test_turn_crash_is_reported():
    h = Harness()

    async def boom(*_args):
        raise RuntimeError("kaput")

    h.router._start_turn = boom
    await h.router.delegate("x")
    await _settle(h.router)
    assert "kaput" in h.spoken[0]
    assert h.working == [True, False]


async def test_empty_request_is_rejected():
    h = Harness()
    assert (await h.router.delegate("   ")).startswith("error")


def test_build_delegation_escapes_and_clips():
    text = build_delegation("<b>hi</b>", "user: " + "长" * 5000)
    assert "&lt;b&gt;hi&lt;/b&gt;" in text
    assert len(text.encode()) < 4096 * 2 + 200
    assert "<transcript_delta>" not in build_delegation("x", "  ")


async def test_steering_an_externally_owned_turn_observes_and_reports_completion():
    hold = asyncio.Event()
    h = Harness(
        busy=True,
        hold=hold,
        chunks=[sse('{"type":"TEXT_MESSAGE_CONTENT","delta":"external answer"}')],
    )
    h.say("a:1", "add a conclusion")
    result = await h.router.delegate("add a conclusion")
    assert result.startswith("steered")
    assert h.router.working is True
    hold.set()
    await _settle(h.router)
    assert h.working == [True, False]
    assert len(h.spoken) == 1 and "external answer" in h.spoken[0]


async def test_default_start_turn_preserves_chat_config_and_dispatches_acp(monkeypatch):
    from types import SimpleNamespace
    import suzent.acp.runtime as acp_runtime
    import suzent.agent_manager as agent_manager
    import suzent.database as database_mod
    import suzent.routes.chat_routes as chat_routes

    fake_chat = SimpleNamespace(
        config={
            "runtime": "acp",
            "acp_agent_id": "codex",
            "model": "custom/model",
            "sandbox_enabled": False,
        }
    )
    monkeypatch.setattr(
        database_mod,
        "get_database",
        lambda: SimpleNamespace(get_chat=lambda _cid: fake_chat),
    )
    monkeypatch.setattr(
        chat_routes, "_prewrite_user_display_message", lambda *_a, **_k: True
    )
    seen_build_cfg: list[dict] = []

    def fake_build_agent_config(cfg, **_kw):
        seen_build_cfg.append(dict(cfg))
        return {**cfg, "built": True}

    monkeypatch.setattr(agent_manager, "build_agent_config", fake_build_agent_config)
    acp_calls: list[tuple[str, str, dict, bool]] = []

    async def fake_stream_acp_turn(
        chat_id, message, cfg, *, replay=None, prewritten=False, **_kw
    ):
        acp_calls.append((chat_id, message, cfg, prewritten))
        yield sse('{"type":"TEXT_MESSAGE_CONTENT","delta":"acp reply"}')

    monkeypatch.setattr(acp_runtime, "stream_acp_turn", fake_stream_acp_turn)

    spoken: list[str] = []

    async def noop_context(_t: str) -> None:
        pass

    router = HandoffRouter(
        "acp-chat",
        send_context=noop_context,
        enqueue_spoken=spoken.append,
        transcript_grace=0.01,
    )
    assert (await router.delegate("fix the bug")).startswith("started")
    await _settle(router)
    assert seen_build_cfg and seen_build_cfg[0]["model"] == "custom/model"
    assert len(acp_calls) == 1
    assert acp_calls[0][0] == "acp-chat"
    assert acp_calls[0][1] == "fix the bug"
    assert acp_calls[0][2]["acp_agent_id"] == "codex"
    assert acp_calls[0][2]["built"] is True
    assert acp_calls[0][3] is True
    assert spoken and "acp reply" in spoken[0]


async def test_resumed_approval_stream_on_bus_clears_approval_and_speaks_result():
    from suzent.core.stream_registry import (
        register_background_stream,
        unregister_background_stream,
    )

    context: list[str] = []
    spoken: list[str] = []
    working: list[bool] = []

    async def send_context(text: str) -> None:
        context.append(text)

    async def on_working(active: bool) -> None:
        working.append(active)

    async def first_turn(_msg: str, _rem: list[str], on_chunk) -> None:
        await on_chunk(sse('{"type":"CUSTOM","name":"tool_approval_request"}'))

    router = HandoffRouter(
        "approval-chat",
        send_context=send_context,
        enqueue_spoken=spoken.append,
        on_working=on_working,
        start_turn=first_turn,
        progress_interval=0,
        transcript_grace=0.01,
    )
    router.start_watching()
    try:
        assert (await router.delegate("run bash")).startswith("started")
        await _settle(router)
        assert len(spoken) == 1 and "approval" in spoken[0]

        # Simulate the user clicking Approve in the UI (/chat/send with resume_approvals).
        queue = register_background_stream("approval-chat")
        await asyncio.sleep(0.02)
        await queue.put(
            sse('{"type":"CUSTOM","name":"tool_permission_resolution","value":{}}')
        )
        await queue.put(
            sse('{"type":"TEXT_MESSAGE_CONTENT","delta":"approved and finished"}')
        )
        unregister_background_stream("approval-chat", queue)
        await _settle(router)

        assert any("Approval resolved" in c for c in context)
        assert len(spoken) == 2 and "approved and finished" in spoken[1]
        assert working == [True, False, True, False]
    finally:
        router.close()


async def test_in_stream_acp_permission_clears_when_execution_resumes():
    h = Harness(
        chunks=[
            sse(
                '{"type":"CUSTOM","name":"acp.permission_request","value":{"requestId":"p1"}}'
            ),
            sse(
                '{"type":"CUSTOM","name":"acp.permission_request","value":{"requestId":"p1","resolved":"approved"}}'
            ),
            sse(
                '{"type":"TEXT_MESSAGE_CONTENT","delta":"acp finished after approval"}'
            ),
        ]
    )
    h.say("u1", "edit file")
    await h.router.delegate("edit file")
    await _settle(h.router)
    assert len(h.spoken) == 2
    assert "approval" in h.spoken[0]
    assert "acp finished after approval" in h.spoken[1]
    assert any("Approval resolved" in c for c in h.context)


async def test_fast_resumed_stream_completed_before_watcher_wakes_is_observed():
    from suzent.core.stream_registry import (
        register_background_stream,
        unregister_background_stream,
    )

    spoken: list[str] = []

    async def noop_context(_t: str) -> None:
        pass

    async def first_turn(_msg: str, _rem: list[str], on_chunk) -> None:
        await on_chunk(sse('{"type":"CUSTOM","name":"tool_approval_request"}'))

    router = HandoffRouter(
        "fast-approval-chat",
        send_context=noop_context,
        enqueue_spoken=spoken.append,
        start_turn=first_turn,
        progress_interval=0,
        transcript_grace=0.01,
    )
    router.start_watching()
    await asyncio.sleep(0)
    try:
        assert (await router.delegate("run bash")).startswith("started")
        await _settle(router)
        assert len(spoken) == 1 and "approval" in spoken[0]

        # Register, emit answer, and finish synchronously before yielding to the watcher.
        queue = register_background_stream("fast-approval-chat")
        queue.put_nowait(
            sse('{"type":"TEXT_MESSAGE_CONTENT","delta":"instant resumed answer"}')
        )
        unregister_background_stream("fast-approval-chat", queue)

        await asyncio.sleep(0.02)
        await _settle(router)
        assert len(spoken) == 2 and "instant resumed answer" in spoken[1]
    finally:
        router.close()


async def test_snapshot_replay_suppresses_already_resolved_acp_permission_prompt():
    from suzent.core.stream_registry import (
        register_background_stream,
        unregister_background_stream,
    )

    spoken: list[str] = []

    async def noop_context(_t: str) -> None:
        pass

    queue = register_background_stream("acp-replay-chat")
    try:
        queue.put_nowait(
            sse(
                '{"type":"CUSTOM","name":"acp.permission_request","value":{"requestId":"p1"}}'
            )
        )
        queue.put_nowait(
            sse(
                '{"type":"CUSTOM","name":"acp.permission_request","value":{"requestId":"p1","resolved":"approved"}}'
            )
        )
        router = HandoffRouter(
            "acp-replay-chat",
            send_context=noop_context,
            enqueue_spoken=spoken.append,
            progress_interval=0,
        )
        router.attach_if_busy()
        await asyncio.sleep(0.02)
        assert spoken == []

        queue.put_nowait(
            sse('{"type":"TEXT_MESSAGE_CONTENT","delta":"final acp answer"}')
        )
        unregister_background_stream("acp-replay-chat", queue)
        await _settle(router)
        assert len(spoken) == 1 and "final acp answer" in spoken[0]
    finally:
        unregister_background_stream("acp-replay-chat", queue)
