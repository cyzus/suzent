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


async def test_delegate_returns_at_once_and_records_the_users_own_words():
    h = Harness(chunks=[sse('{"type":"TEXT_MESSAGE_CONTENT","delta":"晴天"}')])
    h.say("a:1", "今天伦敦天气怎么样")
    result = await h.router.delegate("Check London weather today")
    assert result.startswith("started")
    await _settle(h.router)

    message, reminders = h.turns[0]
    # The chat row is what the user said, not the front desk's paraphrase.
    assert message == "今天伦敦天气怎么样"
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
    assert h.turns[0][0] == "late words"


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
