"""Hand realtime voice requests to the main Suzent agent without waiting for it.

The voice model (the "front desk") talks; the main agent works. A delegation
returns at once -- ``started`` when a new turn begins, ``steered`` when the
request is injected into the turn already running -- so the conversation keeps
going while Suzent works, and a barge-in that cancels the front desk's tool
call cannot cancel the turn: it runs in its own task.

While the turn runs, its tool activity is fed back to the front desk as silent
``[BACKEND]`` context; when it ends, the result is queued for the front desk to
speak once it is idle.
"""

from __future__ import annotations

import asyncio
import html
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from suzent.logger import get_logger

logger = get_logger(__name__)

# Codex caps each delegation section at 4 KiB; so do we.
_SECTION_LIMIT = 4096
# Front-desk context per completion: the final answer, truncated.
_RESULT_LIMIT = 4000
# Coalescing window for progress context sent to the front desk.
PROGRESS_INTERVAL = 0.2
# How long a delegation waits for the user's own finalized words when the model
# called the tool before the provider delivered the transcript (Gemini 3.x
# finalizes ~1.4s after speech ends).
TRANSCRIPT_GRACE = 1.5

VOICE_TURN_REMINDER = (
    "This request came from the realtime voice front desk, which will read a short "
    "summary of your final answer aloud. Work as usual in this chat (approvals "
    "belong in the Suzent window), but lead your final answer with the conclusion "
    "in one or two plain sentences; details, code and links can follow below."
)

_ALREADY_DELEGATED = (
    "already_delegated: Suzent is already working on this request. "
    "Do not call delegate again for it; wait for the result."
)

# Turns kept alive past the voice session that started them. A delegated turn
# is an ordinary chat turn: ending the voice session must not cancel it.
_running_turns: set[asyncio.Task[Any]] = set()


def _clip(text: str, limit: int = _SECTION_LIMIT) -> str:
    """Keep the tail of *text* within *limit* UTF-8 bytes; the latest words matter most."""
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    return "…" + data[-limit:].decode("utf-8", errors="ignore")


def build_delegation(request: str, transcript_delta: str) -> str:
    """Render the main agent's input in the Codex ``<realtime_delegation>`` shape."""
    parts = [
        "<realtime_delegation>",
        f"<input>{html.escape(_clip(request.strip()), quote=False)}</input>",
    ]
    if transcript_delta.strip():
        parts.append(
            "<transcript_delta>"
            f"{html.escape(_clip(transcript_delta.strip()), quote=False)}"
            "</transcript_delta>"
        )
    parts.append("</realtime_delegation>")
    return "\n".join(parts)


def _decode_sse(chunk: Any) -> dict[str, Any]:
    if not isinstance(chunk, str) or not chunk.startswith("data: "):
        return {}
    try:
        value = json.loads(chunk[6:].strip() or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


@dataclass
class TurnOutcome:
    text: str = ""
    failure: str | None = None
    approval_pending: bool = False
    tools: list[str] = field(default_factory=list)


class HandoffRouter:
    """Route front-desk delegations into one chat's main-agent turns.

    Everything that touches the outside world is injectable so tests can drive
    the router without a model, a database or a voice provider:

    - ``send_context(text)``: silent context for the front desk.
    - ``enqueue_spoken(text)``: a message the front desk should answer when idle.
    - ``on_working(active)``: tell the client whether Suzent is working.
    - ``transcript_delta()``: voice lines said since the last delegation.
    - ``start_turn(content, on_chunk)``: run a new turn; defaults to ChatProcessor.
    - ``inject(content)``: hand content to the live turn; defaults to the
      stream control's injector. ``None`` means nothing could take it.
    - ``is_busy()``: whether any producer owns the chat's stream.
    """

    def __init__(
        self,
        chat_id: str,
        *,
        send_context: Callable[[str], Awaitable[None]],
        enqueue_spoken: Callable[[str], None],
        on_working: Callable[[bool], Awaitable[None]] | None = None,
        transcript_delta: Callable[[], list[tuple[str, str]]] | None = None,
        start_turn: Callable[
            [str, list[str], Callable[[str], Awaitable[None]]], Awaitable[None]
        ]
        | None = None,
        observe_turn: Callable[[Callable[[str], Awaitable[None]]], Awaitable[None]]
        | None = None,
        inject: Callable[[str], str | None] | None = None,
        is_busy: Callable[[], bool] | None = None,
        stop: Callable[[], bool] | None = None,
        progress_interval: float = PROGRESS_INTERVAL,
        transcript_grace: float = TRANSCRIPT_GRACE,
    ) -> None:
        self.chat_id = chat_id
        self._send_context = send_context
        self._enqueue_spoken = enqueue_spoken
        self._on_working = on_working
        self._transcript_delta = transcript_delta or (lambda: [])
        self._transcript_grace = transcript_grace
        # Set whenever a user utterance is finalized; a delegation that arrives
        # before its own words briefly waits for them.
        self._utterance_seen = asyncio.Event()
        self._delegating = False
        self._start_turn = start_turn or self._default_start_turn
        self._observe_turn = observe_turn or self._default_observe_turn
        self._inject = inject or self._default_inject
        self._is_busy = is_busy or self._default_is_busy
        self._stop = stop or self._default_stop
        self._progress_interval = progress_interval
        self._task: asyncio.Task[Any] | None = None
        self._observer_task: asyncio.Task[Any] | None = None
        self._closed = False
        # The request the last delegation in this call handled. The front desk
        # may call `delegate` several times for one sentence; only the first
        # one starts work.
        self._last_request: str | None = None
        self._current_utterance: str | None = None
        self._pending_progress: list[str] = []
        self._last_flush = 0.0
        self._flush_handle: asyncio.TimerHandle | None = None

    # -- signals from the bridge -------------------------------------------------

    def note_user_utterance(self, utterance_id: str) -> None:
        """A user utterance was finalized: later delegations belong to it."""
        self._current_utterance = utterance_id
        self._utterance_seen.set()

    @property
    def working(self) -> bool:
        return (self._task is not None and not self._task.done()) or (
            self._observer_task is not None and not self._observer_task.done()
        )

    def attach_if_busy(self, *, notify_start: bool = False) -> None:
        """Observe an externally owned turn so completion is reported to this call."""
        if self._closed or self.working or not self._is_busy():
            return
        self._observer_task = asyncio.create_task(
            self._run_observed(notify_start=notify_start)
        )

    def close(self) -> None:
        """The voice session ended. The running turn keeps going, unobserved."""
        self._closed = True
        if self._observer_task is not None and not self._observer_task.done():
            self._observer_task.cancel()
        if self._flush_handle is not None:
            self._flush_handle.cancel()
            self._flush_handle = None

    # -- front-desk tools --------------------------------------------------------

    async def delegate(self, request: str) -> str:
        request = (request or "").strip()
        if not request:
            return "error: empty request. Ask the user what they need."
        if self._delegating:
            return _ALREADY_DELEGATED
        self._delegating = True
        try:
            # Decide "same request again" only after the user's words had their
            # chance to arrive: providers that finalize the transcript after the
            # tool call would otherwise make a new request look like a repeat
            # of the previous utterance, and it would be dropped, not steered.
            lines = await self._take_lines()
            new_words = any(speaker == "user" for speaker, _ in lines)
            # No new words after an earlier delegation in this call: a repeat
            # if something is still running (ours, or a turn that outlived an
            # earlier call) or if it asks for the same thing again.
            if (
                not new_words
                and self._last_request is not None
                and (self.working or self._is_busy() or request == self._last_request)
            ):
                return _ALREADY_DELEGATED
            return await self._delegate(request, lines)
        finally:
            self._delegating = False

    async def _delegate(self, request: str, lines: list[tuple[str, str]]) -> str:
        # The chat shows what the user actually said; the front desk's reading
        # of it travels as a hidden reminder. Typed-in-voice and spoken lines
        # are both "user" lines.
        words = " ".join(text for speaker, text in lines if speaker == "user").strip()
        message = words or request
        delta = "\n".join(f"{speaker}: {text}" for speaker, text in lines)
        if self.working or self._is_busy():
            steer = message
            if words and words != request:
                steer = f"{words}\n(Voice front desk read this as: {request})"
            if self._inject(steer) is not None:
                self._last_request = request
                if not self.working:
                    self.attach_if_busy(notify_start=True)
                return (
                    "steered: the request was added to the task Suzent is already "
                    "running. Tell the user in a few words; do not answer it yourself."
                )
            return (
                "busy: Suzent is finishing another task in this chat and could not "
                "take this request yet. Ask the user to try again in a moment."
            )
        self._last_request = request
        reminders = [VOICE_TURN_REMINDER, build_delegation(request, delta)]
        self._task = asyncio.create_task(self._run(message, reminders))
        _running_turns.add(self._task)
        self._task.add_done_callback(_running_turns.discard)
        return (
            "started: Suzent is working on it in the chat window. Tell the user in "
            "a few words that it is on it; do not answer the request yourself. "
            "The result will arrive later as a <system> message."
        )

    async def cancel_task(self) -> str:
        if not (self.working or self._is_busy()):
            return "nothing_running: Suzent is not working on anything."
        self._stop()
        return "cancelled: Suzent was asked to stop. Tell the user briefly."

    # -- the delegated turn --------------------------------------------------------

    async def _take_lines(self) -> list[tuple[str, str]]:
        """Voice lines since the last delegation, waiting briefly for the user's.

        Some providers finalize the user's transcript after the model has
        already called the tool; without the wait those words would be
        attributed to the *next* request.
        """
        lines = list(self._transcript_delta())
        if not any(speaker == "user" for speaker, _ in lines):
            self._utterance_seen.clear()
            try:
                await asyncio.wait_for(
                    self._utterance_seen.wait(), timeout=self._transcript_grace
                )
            except asyncio.TimeoutError:
                pass
            lines += self._transcript_delta()
        self._utterance_seen.clear()
        return lines

    async def _run(self, message: str, reminders: list[str]) -> None:
        outcome = TurnOutcome()
        await self._notify_working(True)
        try:

            async def on_chunk(chunk: str) -> None:
                self._observe(chunk, outcome)

            await self._start_turn(message, reminders, on_chunk)
        except asyncio.CancelledError:
            outcome.failure = outcome.failure or "the task was stopped"
            raise
        except Exception as exc:
            logger.warning("Voice delegated turn failed: {}", exc)
            outcome.failure = str(exc) or type(exc).__name__
        finally:
            await self._flush_progress()
            await self._notify_working(False)
            self._report(outcome)

    async def _run_observed(self, *, notify_start: bool = False) -> None:
        outcome = TurnOutcome()
        if notify_start:
            await self._notify_working(True)
        try:

            async def on_chunk(chunk: str) -> None:
                self._observe(chunk, outcome)

            await self._observe_turn(on_chunk)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Voice observed turn failed: {}", exc)
            outcome.failure = str(exc) or type(exc).__name__
        finally:
            if not self._closed:
                await self._flush_progress()
                await self._notify_working(False)
                self._report(outcome)

    def _observe(self, chunk: str, outcome: TurnOutcome) -> None:
        event = _decode_sse(chunk)
        kind = event.get("type")
        if kind == "TEXT_MESSAGE_CONTENT":
            outcome.text += str(event.get("delta") or "")
        elif kind == "TEXT_MESSAGE_START":
            # Only the last message is the answer; earlier ones were narration
            # between tool calls.
            outcome.text = ""
        elif kind == "TOOL_CALL_START":
            name = str(event.get("toolCallName") or event.get("tool_call_name") or "")
            if name:
                outcome.tools.append(name)
                self._queue_progress(f"[BACKEND] Suzent is running {name}.")
        elif kind == "RUN_ERROR":
            outcome.failure = str(event.get("message") or "the task failed")
        elif kind == "CUSTOM" and event.get("name") == "tool_approval_request":
            outcome.approval_pending = True
            self._queue_progress("[BACKEND] Suzent is waiting for the user's approval.")

    def _report(self, outcome: TurnOutcome) -> None:
        if self._closed:
            return
        if outcome.approval_pending:
            message = (
                "Suzent paused: an action needs the user's approval in the Suzent "
                "window. Tell the user briefly."
            )
        elif outcome.failure:
            message = (
                f"Suzent could not finish: {_clip(outcome.failure, 600)}. "
                "Tell the user briefly."
            )
        else:
            text = outcome.text.strip() or "(no text answer; see the chat window)"
            message = (
                "Suzent finished. Its answer, shown in full in the chat window:\n"
                f"{_clip(text, _RESULT_LIMIT)}\n"
                "Summarize it for the user in one to three short spoken sentences, in "
                "their language. Never read code, URLs or long lists aloud."
            )
        try:
            self._enqueue_spoken(f"<system>{message}</system>")
        except Exception as exc:  # the session may be closing
            logger.debug("Voice completion could not be queued: {}", exc)

    # -- progress coalescing -----------------------------------------------------

    def _queue_progress(self, line: str) -> None:
        if self._closed:
            return
        self._pending_progress.append(line)
        if self._flush_handle is not None:
            return
        delay = max(0.0, self._last_flush + self._progress_interval - time.monotonic())
        loop = asyncio.get_running_loop()
        self._flush_handle = loop.call_later(
            delay, lambda: asyncio.ensure_future(self._flush_progress())
        )

    async def _flush_progress(self) -> None:
        if self._flush_handle is not None:
            self._flush_handle.cancel()
            self._flush_handle = None
        lines, self._pending_progress = self._pending_progress, []
        if not lines or self._closed:
            return
        self._last_flush = time.monotonic()
        try:
            await self._send_context(_clip("\n".join(dict.fromkeys(lines)), 2000))
        except Exception as exc:
            logger.debug("Voice progress context failed: {}", exc)

    async def _notify_working(self, active: bool) -> None:
        if self._on_working is None or self._closed:
            return
        try:
            await self._on_working(active)
        except Exception as exc:
            logger.debug("Voice working notification failed: {}", exc)

    # -- defaults wired to the real runtime ----------------------------------------

    async def _default_start_turn(
        self,
        content: str,
        reminders: list[str],
        on_chunk: Callable[[str], Awaitable[None]],
    ) -> None:
        from suzent.agent_manager import build_agent_config
        from suzent.config import CONFIG
        from suzent.core.chat_processor import ChatProcessor
        from suzent.core.stream_registry import (
            bind_producer_replay,
            register_background_stream,
        )
        from suzent.database import get_database
        from suzent.routes.chat_routes import (
            _prewrite_user_display_message,
            _resolve_chat_runtime,
            _sanitized_for_display_and_turn,
        )

        def _load_chat_config() -> tuple[dict[str, Any], str]:
            chat = get_database().get_chat(self.chat_id)
            cfg = (
                dict(chat.config or {})
                if chat and isinstance(chat.config, dict)
                else {}
            )
            runtime = _resolve_chat_runtime(self.chat_id, cfg)
            return cfg, runtime

        chat_config, effective_runtime = await asyncio.to_thread(_load_chat_config)
        config_override = build_agent_config(chat_config, require_social_tool=False)
        sanitized = _sanitized_for_display_and_turn(content)

        # The same path as /chat/send: the user row is written up front through
        # the revision-safe helper, and the turn streams on the background bus,
        # where the chat window attaches on `stream_started`.
        prewritten = await asyncio.to_thread(
            _prewrite_user_display_message, self.chat_id, sanitized, []
        )
        queue = register_background_stream(self.chat_id)
        try:
            bind_producer_replay(queue.replay)
            if effective_runtime == "acp":
                from suzent.acp.runtime import stream_acp_turn

                generator = stream_acp_turn(
                    self.chat_id,
                    sanitized,
                    {**chat_config, **config_override},
                    replay=queue.replay,
                    prewritten=bool(prewritten),
                )
            else:
                generator = ChatProcessor().process_turn(
                    chat_id=self.chat_id,
                    user_id=CONFIG.user_id,
                    message_content=sanitized,
                    config_override=config_override,
                    system_reminders=reminders,
                )
            async for chunk in generator:
                await queue.put(chunk)
                await on_chunk(chunk)
        except Exception as exc:
            payload = (
                f"data: {json.dumps({'type': 'RUN_ERROR', 'message': str(exc)})}\n\n"
            )
            try:
                await queue.put(payload)
            except Exception:
                pass
            raise
        finally:
            await queue.put(None)

    async def _default_observe_turn(
        self,
        on_chunk: Callable[[str], Awaitable[None]],
    ) -> None:
        from suzent.core.stream_registry import (
            get_background_queue,
            is_background_streaming,
            register_bus_subscriber,
            unregister_bus_subscriber,
        )

        sub = register_bus_subscriber()
        try:
            queue = get_background_queue(self.chat_id)
            if queue is not None:
                for event in queue.replay._snapshot_events():
                    await on_chunk(f"data: {json.dumps(event)}\n\n")
            while is_background_streaming(self.chat_id):
                try:
                    item = await asyncio.wait_for(sub.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if item is None:
                    break
                if item.get("chat_id") != self.chat_id:
                    continue
                if item.get("event") == "chunk":
                    data = item.get("data")
                    if isinstance(data, str):
                        await on_chunk(data)
                elif item.get("event") == "stream_ended":
                    break
        finally:
            unregister_bus_subscriber(sub)

    def _default_inject(self, content: str) -> str | None:
        from suzent.core.chat_processor import build_steering_text
        from suzent.core.stream_registry import stream_controls

        control = stream_controls.get(self.chat_id)
        inject = getattr(control, "inject", None) if control is not None else None
        if inject is None:
            return None
        return inject(build_steering_text(content))

    def _default_is_busy(self) -> bool:
        from suzent.core.stream_registry import is_background_streaming

        return is_background_streaming(self.chat_id)

    def _default_stop(self) -> bool:
        from suzent.core.stream_registry import stop_stream

        return stop_stream(self.chat_id, reason="Stopped by voice request")
