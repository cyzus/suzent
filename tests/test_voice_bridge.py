import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import Mock

from pydantic_ai import Agent
from pydantic_ai.messages import PartEndEvent, SpeechPart
from pydantic_ai.realtime import (
    RealtimeModel,
    RealtimeInputSpeechStartEvent,
    RealtimeResponseInterruptedEvent,
    RealtimeSessionErrorEvent,
    RealtimeTurnCompleteEvent,
)

from suzent.voice.realtime import MissingApiKey, VoiceBridge


class FakeWebSocket:
    def __init__(self, incoming=()):
        self.sent = []
        self.closed = False
        self._incoming = asyncio.Queue()
        for item in incoming:
            self._incoming.put_nowait(item)

    async def send_json(self, message):
        self.sent.append(message)

    async def send_bytes(self, chunk):
        self.sent.append(chunk)

    async def receive(self):
        return await self._incoming.get()

    async def close(self):
        self.closed = True

    def stop(self):
        self._incoming.put_nowait(
            {"type": "websocket.receive", "text": '{"type":"stop"}'}
        )

    def json(self, kind=None):
        return [
            m
            for m in self.sent
            if isinstance(m, dict) and (kind is None or m.get("type") == kind)
        ]


def update(index, speaker, text):
    return SimpleNamespace(index=index, speaker=speaker, transcript=text, delta=text)


class FakeSession:
    audio_input_sample_rate = 16000
    audio_output_sample_rate = 24000

    def __init__(self, events=(), transcripts=(), audio=()):
        self.events = list(events)
        self.transcripts = list(transcripts)
        self.audio_out = list(audio)
        self.audio = []
        self.interrupts = []
        self.sent = []
        self.queued = []

    async def send_audio(self, data):
        self.audio.append(data)

    async def send(self, content, respond=None):
        self.sent.append((content, respond))

    def enqueue(self, *content, priority="asap"):
        self.queued.append((content, priority))
        return "q"

    async def interrupt(self, played_ms=0):
        self.interrupts.append(played_ms)

    async def stream_audio(self):
        for chunk in self.audio_out:
            await asyncio.sleep(0.01)
            yield chunk
        await asyncio.Event().wait()
        yield b""  # pragma: no cover

    async def stream_transcripts(self, delta=True):
        assert delta
        for item in self.transcripts:
            await asyncio.sleep(0.01)
            yield item
        await asyncio.Event().wait()
        yield None  # pragma: no cover

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        # Let the transcript stream go first, as providers do.
        await asyncio.sleep(0.1)
        for event in self.events:
            await asyncio.sleep(0.01)
            yield event
        await asyncio.Event().wait()


def make_bridge(ws, session, *, startup=(), saved=None, chat_id="chat-1"):
    exited = []

    @asynccontextmanager
    async def factory():
        try:
            yield session
        finally:
            exited.append(True)

    bridge = VoiceBridge(
        ws,
        chat_id,
        session_factory=factory,
        model_id="gemini/gemini-3.8-live",
        startup_messages=list(startup),
        persist=(saved.extend if saved is not None else (lambda _e: None)),
        router_options={"is_busy": lambda: False},
    )
    bridge.exited = exited
    return bridge


async def run_for(bridge, ws, seconds=0.4):
    task = asyncio.create_task(bridge.run())
    await asyncio.sleep(seconds)
    ws.stop()
    await asyncio.wait_for(task, 2)


def test_real_session_factory_uses_supported_session_api(monkeypatch):
    from suzent.voice import realtime

    model = Mock(spec=RealtimeModel)
    model.settings = {}
    monkeypatch.setattr(
        realtime, "resolve_realtime_model", lambda _settings: ("test", model)
    )
    monkeypatch.setattr(realtime, "build_front_desk_agent", lambda _router: Agent())
    bridge = make_bridge(FakeWebSocket(), FakeSession())

    context = bridge._real_session_factory()()

    assert hasattr(context, "__aenter__")
    assert hasattr(context, "__aexit__")


async def test_live_and_final_transcripts_share_one_line_and_are_cleaned():
    saved = []
    ws = FakeWebSocket()
    session = FakeSession(
        transcripts=[
            update(1, "user", "今天 天气"),
            update(1, "user", "今天 天气 怎么样"),
        ],
        events=[
            PartEndEvent(
                index=1, part=SpeechPart(speaker="user", transcript="今天天气怎么样?")
            ),
            # A stale delta after the final must not shrink the line.
            PartEndEvent(index=1, part=SpeechPart(speaker="user", transcript="今天")),
            RealtimeTurnCompleteEvent(),
        ],
    )
    bridge = make_bridge(ws, session, saved=saved)
    await run_for(bridge, ws)

    lines = ws.json("transcript")
    assert {line["id"] for line in lines} == {f"{bridge._key}:1"}
    assert [line["text"] for line in lines] == [
        "今天天气",
        "今天天气怎么样",
        "今天天气怎么样？",
    ]
    assert [line["final"] for line in lines] == [False, False, True]
    # Persisted once, as the final text.
    assert [entry["text"] for entry in saved] == ["今天天气怎么样？"]
    states = [m["state"] for m in ws.json("state")]
    assert states[:4] == ["listening", "user_speaking", "thinking", "listening"]


async def test_line_ids_do_not_collide_across_sessions():
    ids = []
    for _ in range(2):
        ws = FakeWebSocket()
        session = FakeSession(transcripts=[update(0, "user", "hi")])
        await run_for(make_bridge(ws, session), ws, 0.15)
        ids += [m["id"] for m in ws.json("transcript")]
    assert len(set(ids)) == 2


async def test_states_come_from_audio_and_turn_completion():
    ws = FakeWebSocket()
    session = FakeSession(
        audio=[b"a", b"b"],
        events=[RealtimeTurnCompleteEvent(), RealtimeInputSpeechStartEvent()],
    )
    await run_for(make_bridge(ws, session), ws)
    states = [m["state"] for m in ws.json("state")]
    assert states == ["listening", "speaking", "listening", "user_speaking"]
    assert ws.sent.count(b"a") == 1 and ws.sent.count(b"b") == 1


async def test_startup_context_is_sent_silently_before_ready():
    ws = FakeWebSocket()
    session = FakeSession()
    bridge = make_bridge(
        ws, session, startup=[{"role": "user", "content": "earlier question"}]
    )
    await run_for(bridge, ws, 0.1)
    content, respond = session.sent[0]
    assert "earlier question" in content and respond is False
    assert ws.json()[0]["type"] == "ready"
    assert ws.json()[0]["live_captions"] is False


async def test_typed_text_is_recorded_and_sent_to_the_model():
    saved = []
    ws = FakeWebSocket(
        [{"type": "websocket.receive", "text": '{"type":"text","text":" 打字 "}'}]
    )
    session = FakeSession()
    bridge = make_bridge(ws, session, saved=saved)
    await run_for(bridge, ws, 0.15)
    assert ("打字", None) in session.sent
    assert saved[0]["text"] == "打字" and saved[0]["speaker"] == "user"
    assert bridge.take_transcript_delta() == [("user", "打字")]


async def test_interrupted_and_errors():
    ws = FakeWebSocket()
    session = FakeSession(
        events=[
            RealtimeResponseInterruptedEvent(),
            RealtimeSessionErrorEvent("boom", recoverable=True),
        ]
    )
    await run_for(make_bridge(ws, session), ws)
    assert ws.json("interrupted")
    assert ws.json("error")[0]["message"] == "boom"
    assert ws.sent[-1] == {"type": "closed"}


async def test_fatal_session_error_ends_the_session():
    ws = FakeWebSocket()
    session = FakeSession(events=[RealtimeSessionErrorEvent("gone", recoverable=False)])
    bridge = make_bridge(ws, session)
    await asyncio.wait_for(bridge.run(), 2)
    assert ws.sent[-1] == {"type": "closed"}
    assert bridge.exited and ws.closed


async def test_bad_control_messages_are_ignored():
    huge = '{"type":"stop","pad":"' + "x" * 10_000 + '"}'
    ws = FakeWebSocket(
        [
            {"type": "websocket.receive", "text": "not json"},
            {"type": "websocket.receive", "text": "[1,2]"},
            {"type": "websocket.receive", "text": huge},
            {
                "type": "websocket.receive",
                "text": '{"type":"interrupt","played_ms":"x"}',
            },
            {"type": "websocket.receive", "text": '{"type":"text","text":""}'},
            {"type": "websocket.receive", "text": '{"type":"stop"}'},
        ]
    )
    session = FakeSession()
    bridge = make_bridge(ws, session)
    await asyncio.wait_for(bridge.run(), 2)
    assert session.interrupts == [0]
    assert session.sent == []
    assert bridge.exited


async def test_client_info_is_logged_trimmed_and_changes_nothing(monkeypatch):
    from suzent.voice import realtime

    logged = []
    monkeypatch.setattr(
        realtime.logger, "info", lambda fmt, *args: logged.append(fmt.format(*args))
    )
    info = {
        "event": "mic",
        "echo_cancellation": False,
        "device": "x" * 500,
        "nested": {"a": 1},
    }
    ws = FakeWebSocket(
        [
            {
                "type": "websocket.receive",
                "text": json.dumps({"type": "client_info", "info": info}),
            },
            {"type": "websocket.receive", "text": '{"type":"client_info","info":7}'},
            {"type": "websocket.receive", "text": '{"type":"stop"}'},
        ]
    )
    session = FakeSession()
    bridge = make_bridge(ws, session)
    await asyncio.wait_for(bridge.run(), 2)
    assert session.sent == [] and session.interrupts == []
    client_lines = [line for line in logged if " client: " in line]
    assert len(client_lines) == 2
    assert "'echo_cancellation': False" in client_lines[0]
    assert "nested" not in client_lines[0]
    assert "x" * 81 not in client_lines[0]
    assert client_lines[1].endswith("client: {}")


async def test_client_disconnect_cleans_up():
    ws = FakeWebSocket([{"type": "websocket.disconnect"}])
    bridge = make_bridge(ws, FakeSession())
    await asyncio.wait_for(bridge.run(), 2)
    assert bridge.exited


async def test_typed_start_errors_are_reported():
    @asynccontextmanager
    async def failing():
        raise MissingApiKey("no key")
        yield  # pragma: no cover

    ws = FakeWebSocket()
    await VoiceBridge(ws, "c", session_factory=failing, model_id="m").run()
    assert ws.json("error")[0]["code"] == "no_api_key"
    assert ws.sent[-1] == {"type": "closed"}


async def test_stream_failure_leaks_no_tasks():
    class Failing(FakeSession):
        async def stream_audio(self):
            yield b"one"
            raise RuntimeError("stream died")

    ws = FakeWebSocket()
    bridge = make_bridge(ws, Failing())
    await asyncio.wait_for(bridge.run(), 3)
    await asyncio.sleep(0.05)
    assert [m["code"] for m in ws.json("error")] == ["session_error"]
    assert ws.sent[-1] == {"type": "closed"}
    leaked = [
        t
        for t in asyncio.all_tasks()
        if t is not asyncio.current_task() and not t.done()
    ]
    assert leaked == []


async def test_delegation_end_to_end_through_the_bridge():
    """A spoken request reaches the main agent as the front desk's reading, and
    the answer is queued for the front desk to speak once it is idle."""
    ws = FakeWebSocket()
    session = FakeSession(
        events=[
            PartEndEvent(
                index=2, part=SpeechPart(speaker="user", transcript="帮我 查 天气")
            ),
        ]
    )
    turns = []

    async def start_turn(message, reminders, on_chunk):
        turns.append(message)
        await on_chunk('data: {"type":"TEXT_MESSAGE_CONTENT","delta":"晴"}\n\n')

    bridge = make_bridge(ws, session)
    bridge.router._start_turn = start_turn
    task = asyncio.create_task(bridge.run())
    await asyncio.sleep(0.2)
    assert (await bridge.router.delegate("check weather")).startswith("started")
    await asyncio.wait_for(bridge.router._task, 2)
    ws.stop()
    await asyncio.wait_for(task, 2)

    # The turn's message is the front desk's request, not the raw transcript.
    assert turns == ["check weather"]
    assert [m["active"] for m in ws.json("working")] == [True, False]
    ((content, priority),) = session.queued
    assert "晴" in content[0] and priority == "when_idle"


async def test_interrupt_on_a_model_without_truncation_still_cancels():
    """xAI: no playback-position truncation, so cancel without one."""
    from pydantic_ai.exceptions import UserError

    class NoTruncation(FakeSession):
        async def interrupt(self, played_ms=None):
            if played_ms is not None:
                raise UserError("no truncation")
            self.interrupts.append(None)

    ws = FakeWebSocket(
        [{"type": "websocket.receive", "text": '{"type":"interrupt","played_ms":900}'}]
    )
    session = NoTruncation()
    await run_for(make_bridge(ws, session), ws, 0.15)
    assert session.interrupts == [None]
    assert ws.json("error") == []


async def test_interrupt_on_a_model_without_interruption_keeps_the_call():
    """Gemini Live cannot cancel a reply: the call must survive, and the rest of
    the reply's audio is dropped until the user speaks again."""
    from pydantic_ai.exceptions import UserError

    interrupted = asyncio.Event()

    class NoInterruption(FakeSession):
        async def interrupt(self, played_ms=None):
            interrupted.set()
            raise UserError("no interruption")

        async def stream_audio(self):
            yield b"before"
            await interrupted.wait()
            await asyncio.sleep(0.02)
            yield b"after"
            await asyncio.Event().wait()

    ws = FakeWebSocket()
    session = NoInterruption(events=[])
    bridge = make_bridge(ws, session)
    task = asyncio.create_task(bridge.run())
    await asyncio.sleep(0.05)
    ws._incoming.put_nowait(
        {"type": "websocket.receive", "text": '{"type":"interrupt","played_ms":10}'}
    )
    await asyncio.sleep(0.1)
    assert not task.done()
    assert ws.json("error") == []
    assert ws.json("interrupted")
    assert b"before" in ws.sent and b"after" not in ws.sent
    assert ws.json("state")[-1]["state"] == "listening"
    # The muted reply's words do not keep arriving as captions either.
    await bridge._on_transcript(5, "assistant", "后面没听到的话", False)
    await bridge._on_transcript(5, "assistant", "后面没听到的话。", True)
    assert not any(line["speaker"] == "assistant" for line in ws.json("transcript"))
    # The user speaking again lifts the mute.
    await bridge._on_transcript(7, "user", "再说一次", False)
    assert bridge._muted is False
    ws.stop()
    await asyncio.wait_for(task, 2)
    assert ws.sent[-1] == {"type": "closed"}


class _NoInterruption:
    """Gemini Live: cannot cancel. Exposes the part indices pydantic-ai tracks."""

    def __init__(self, audio_part=None, active_assistant=None):
        from types import SimpleNamespace

        self._audio_part_index = audio_part
        responses = {}
        if active_assistant is not None:
            responses["r"] = SimpleNamespace(open_part_index=active_assistant)
        self._core = SimpleNamespace(_open_responses=responses)

    async def interrupt(self, played_ms=None):
        from pydantic_ai.exceptions import UserError

        raise UserError("no interruption")


def _assistant_lines(ws, saved):
    shown = [m["text"] for m in ws.json("transcript") if m["speaker"] == "assistant"]
    logged = [e["text"] for e in saved if e["speaker"] == "assistant"]
    return shown, logged


def test_realtime_session_still_tracks_the_part_indices_the_cut_relies_on():
    """`_cut_boundary` reads pydantic-ai private state; fail loudly on rename."""
    import inspect

    from pydantic_ai.realtime._core import SessionCore
    from pydantic_ai.realtime._session import RealtimeSession

    session = inspect.getsource(RealtimeSession)
    assert "self._audio_part_index: int | None = None" in session
    assert "self._core = SessionCore(" in session
    core = inspect.getsource(SessionCore)
    assert "self._open_responses: dict[str, _Response] = {}" in core
    assert "response.open_part_index = index = self._take_index()" in core


async def test_cut_reply_stays_out_of_the_log_after_the_user_speaks():
    """Gemini finalizes a cut reply's transcript late, after the user's voice
    already lifted the mute: it must still not reach captions or the log, while
    the next reply does."""
    saved = []
    ws = FakeWebSocket()
    bridge = make_bridge(ws, FakeSession(), saved=saved)
    bridge._replying = True
    # Reply part 3 was streaming captions when the user cut it off; part 4 had
    # started generating too, with no caption yet.
    await bridge._on_transcript(3, "assistant", "前半句", False)
    await bridge._interrupt(_NoInterruption(audio_part=3, active_assistant=4), 10)
    await bridge._on_transcript(5, "user", "停", False)
    assert bridge._muted is False
    await bridge._on_transcript(3, "assistant", "前半句后半句。", True)
    await bridge._on_transcript(4, "assistant", "另一段。", True)
    await bridge._on_transcript(6, "assistant", "好的。", True)
    assert _assistant_lines(ws, saved) == (["前半句", "好的。"], ["好的。"])


async def test_reply_that_starts_before_the_lagging_user_index_is_kept():
    """pydantic-ai claims a user part's index lazily, so the reply to the user's
    words can have a lower index than those words. It must still be shown."""
    saved = []
    ws = FakeWebSocket()
    bridge = make_bridge(ws, FakeSession(), saved=saved)
    bridge._replying = True
    await bridge._on_transcript(3, "assistant", "前半句", False)
    await bridge._interrupt(_NoInterruption(audio_part=3, active_assistant=3), 10)
    await bridge._on_transcript(4, "assistant", "好的", False)  # still muted
    bridge._muted = False  # speech start
    await bridge._on_transcript(5, "user", "停", True)
    await bridge._on_transcript(4, "assistant", "好的，停了。", True)
    await bridge._on_transcript(3, "assistant", "前半句后半句。", True)
    assert _assistant_lines(ws, saved) == (
        ["前半句", "好的，停了。"],
        ["好的，停了。"],
    )


async def test_cut_reply_with_no_caption_yet_is_dropped_after_turn_end():
    """The cut part's index comes from the session, so its late final is
    dropped even though none of its captions arrived while muted."""
    saved = []
    ws = FakeWebSocket()
    bridge = make_bridge(ws, FakeSession(), saved=saved)
    bridge._replying = True
    await bridge._interrupt(_NoInterruption(audio_part=3, active_assistant=3), 10)
    bridge._muted = bridge._replying = False  # turn complete
    await bridge._on_transcript(3, "assistant", "被打断的回复。", True)
    await bridge._on_transcript(7, "assistant", "结果是晴天。", True)
    assert _assistant_lines(ws, saved) == (["结果是晴天。"], ["结果是晴天。"])


async def test_typed_text_does_not_hide_the_next_reply_after_a_cut():
    saved = []
    ws = FakeWebSocket()
    bridge = make_bridge(ws, FakeSession(), saved=saved)
    bridge._replying = True
    await bridge._interrupt(_NoInterruption(audio_part=2, active_assistant=2), 10)
    await bridge._on_transcript(-1, "user", "打字", True)
    await bridge._on_transcript(6, "assistant", "回答", False)
    await bridge._on_transcript(8, "user", "说话", True)
    await bridge._on_transcript(6, "assistant", "回答。", True)
    assert _assistant_lines(ws, saved)[1] == ["回答。"]


async def test_late_interrupt_after_the_turn_ended_does_not_mute_the_next_reply():
    """Stop pressed while the browser still plays a reply whose turn already
    completed: the next reply (e.g. a spoken delegation result) must be heard."""
    from pydantic_ai.exceptions import UserError

    turn_done = asyncio.Event()
    interrupted = asyncio.Event()

    class NoInterruption(FakeSession):
        async def interrupt(self, played_ms=None):
            interrupted.set()
            raise UserError("no interruption")

        async def stream_audio(self):
            yield b"reply-1"
            await turn_done.wait()
            await interrupted.wait()
            await asyncio.sleep(0.02)
            yield b"summary"
            await asyncio.Event().wait()

        async def _iter(self):
            await asyncio.sleep(0.05)
            yield RealtimeTurnCompleteEvent()
            turn_done.set()
            await asyncio.Event().wait()

    ws = FakeWebSocket()
    bridge = make_bridge(ws, NoInterruption())
    task = asyncio.create_task(bridge.run())
    await turn_done.wait()
    await asyncio.sleep(0.02)
    ws._incoming.put_nowait(
        {"type": "websocket.receive", "text": '{"type":"interrupt","played_ms":10}'}
    )
    await asyncio.sleep(0.1)
    assert bridge._muted is False
    assert b"summary" in ws.sent
    ws.stop()
    await asyncio.wait_for(task, 2)
