"""Realtime voice model selection, front-desk agent, and WebSocket bridge."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timezone
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import PartEndEvent, SpeechPart
from pydantic_ai.realtime import (
    RealtimeInputSpeechEndEvent,
    RealtimeInputSpeechStartEvent,
    RealtimeOutputSpeechEndEvent,
    RealtimeResponseInterruptedEvent,
    RealtimeSessionErrorEvent,
    RealtimeTurnCompleteEvent,
)
from pydantic_ai.realtime.model import RealtimeModel
from starlette.websockets import WebSocket, WebSocketDisconnect

from suzent.core.model_registry import get_model_registry
from suzent.core.providers.helpers import get_configured_provider_ids, resolve_api_key
from suzent.logger import get_logger
from suzent.voice.handoff import HandoffRouter
from suzent.voice.settings import VoiceSettings, get_voice_settings

logger = get_logger(__name__)

# Providers pydantic-ai has a realtime adapter for, in auto-selection order.
_REALTIME_PROVIDERS = ("openai", "gemini", "xai", "dashscope")
_REALTIME_ENDPOINT = "/v1/realtime"

_DEFAULT_MODELS = {
    "openai": "openai/gpt-realtime",
    # Measured 2026-10-23 with Chinese speech: simplified text with punctuation,
    # one tool call per request, TurnComplete events, ~1.4s to the transcript.
    "gemini": "gemini/gemini-3.8-live",
    "xai": "xai/grok-voice-latest",
    "dashscope": "dashscope/qwen3.5-omni-flash-realtime",
}

# Qwen-Omni realtime speaks the OpenAI GA protocol, checked live 2026-10-26:
# session.update, text items, tools, and function_call_output all work as-is.
# It hears only 16 kHz PCM, ignores OpenAI's transcription models, and accepts
# conversation.item.truncate without ever applying it.
_DASHSCOPE_TRANSCRIPTION_MODEL = "qwen3-asr-flash-realtime"
_DASHSCOPE_PROFILE = {
    "audio_input_sample_rate": 16000,
    "supports_output_truncation": False,
}

# Whether a model streams the user's words while they speak ("live captions").
# Measured with real audio: Gemini 2.5 native audio emits one update per word;
# the Gemini 3.x live models emit the whole sentence once, after speech ends.
# Models absent here have not been measured, so the UI claims nothing about them.
_LIVE_CAPTIONS: dict[str, bool] = {
    "gemini/gemini-2.5-flash-native-audio-latest": True,
    "gemini/gemini-3.1-flash-live-preview": False,
    "gemini/gemini-3.8-live": False,
}


class RealtimeVoiceError(RuntimeError):
    code = "session_error"


class NoRealtimeModel(RealtimeVoiceError):
    code = "no_model"


class MissingApiKey(RealtimeVoiceError):
    code = "no_api_key"


class UnsupportedProvider(RealtimeVoiceError):
    code = "unsupported_provider"


def _supports_realtime(model_id: str) -> bool:
    caps = get_model_registry().get_capabilities(model_id)
    return caps is not None and _REALTIME_ENDPOINT in caps.supported_endpoints


def list_realtime_options() -> list[dict[str, Any]]:
    """Realtime-capable models on configured providers, like the vision role."""
    configured = get_configured_provider_ids()
    providers = [p for p in _REALTIME_PROVIDERS if p in configured]
    models = [
        model_id
        for model_id in get_model_registry()._capabilities
        if model_id.partition("/")[0] in providers and _supports_realtime(model_id)
    ]
    # Grouped by provider, each provider's default first.
    models.sort(
        key=lambda m: (
            providers.index(m.partition("/")[0]),
            m not in _DEFAULT_MODELS.values(),
            m,
        )
    )
    return [
        {
            "id": model_id,
            "label": model_id,
            "configured": True,
            "live_captions": _LIVE_CAPTIONS.get(model_id),
        }
        for model_id in models
    ]


def resolve_realtime_model(settings: VoiceSettings) -> tuple[str, RealtimeModel]:
    model_id = settings.realtime_model.strip()
    if not model_id:
        for provider in _REALTIME_PROVIDERS:
            if resolve_api_key(provider):
                model_id = _DEFAULT_MODELS[provider]
                break
        if not model_id:
            raise NoRealtimeModel(
                "Configure an OpenAI, Gemini, xAI, or DashScope API key first."
            )

    try:
        provider_id, model_name = model_id.split("/", 1)
    except ValueError as exc:
        raise UnsupportedProvider(
            "Realtime model IDs must use provider/model format."
        ) from exc
    if provider_id not in _REALTIME_PROVIDERS:
        raise UnsupportedProvider(
            f"Realtime voice does not support provider '{provider_id}'."
        )
    if not _supports_realtime(model_id):
        raise UnsupportedProvider(f"Unsupported realtime model '{model_id}'.")

    api_key = resolve_api_key(provider_id)
    if not api_key:
        raise MissingApiKey(f"No API key is configured for {provider_id}.")

    model_settings: Any = {"input_transcription_model": "auto"}
    if settings.realtime_voice:
        voice_key = {
            "openai": "openai_voice",
            "gemini": "google_voice",
            "xai": "xai_voice",
            "dashscope": "openai_voice",
        }[provider_id]
        model_settings[voice_key] = settings.realtime_voice
    language = settings.realtime_language.strip()
    if language and provider_id == "gemini":
        model_settings["google_transcription_language_codes"] = [language]
    sensitivity = settings.realtime_start_sensitivity
    if sensitivity != "auto" and provider_id == "gemini":
        model_settings["google_vad"] = {"start_sensitivity": sensitivity}

    # Provider SDKs are optional extras; import only the one in use.
    if provider_id == "openai":
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.realtime.openai import OpenAIRealtimeModel

        model = OpenAIRealtimeModel(
            model_name,
            provider=OpenAIProvider(api_key=api_key),
            settings=model_settings,
        )
    elif provider_id == "gemini":
        from pydantic_ai.providers.google import GoogleProvider
        from pydantic_ai.realtime.google import GoogleRealtimeModel

        model = GoogleRealtimeModel(
            model_name,
            provider=GoogleProvider(api_key=api_key),
            settings=model_settings,
        )
    elif provider_id == "dashscope":
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.realtime.openai import OpenAIRealtimeModel

        from suzent.core.providers.catalog import PROVIDER_REGISTRY_BY_ID

        chat_base = PROVIDER_REGISTRY_BY_ID["dashscope"].base_url or ""
        model_settings["input_transcription_model"] = _DASHSCOPE_TRANSCRIPTION_MODEL
        model = OpenAIRealtimeModel(
            model_name,
            provider=OpenAIProvider(
                base_url=chat_base.replace("/compatible-mode/v1", "/api-ws/v1"),
                api_key=api_key,
            ),
            settings=model_settings,
            profile=_DASHSCOPE_PROFILE,
        )
    else:
        from pydantic_ai.providers.xai import XaiProvider
        from pydantic_ai.realtime.xai import XaiRealtimeModel

        model = XaiRealtimeModel(
            model_name,
            provider=XaiProvider(api_key=api_key),
            settings=model_settings,
        )
    return model_id, model


FRONT_DESK_INSTRUCTIONS = """You are the voice of Suzent. Suzent is a capable agent working in the chat \
window the user is looking at; you are only its spoken interface.

- Speak in the user's language (Simplified Chinese when they speak Chinese), briefly and naturally.
- You cannot look anything up or take any action yourself. For any request that needs knowledge, \
actions, files, the web, or memory, call `delegate` once, with the request restated clearly and \
completely. `delegate` returns immediately. Then tell the user in a few words that Suzent is on it. \
Never answer such a request yourself and never invent results.
- If the user adds to or corrects a request while Suzent is working, call `delegate` again with the \
addition; it is passed to the running task.
- If the user asks to stop or cancel what Suzent is doing, call `cancel_task`.
- Text starting with [BACKEND] is silent background context. Never reply to it.
- When a <system> message says Suzent finished, summarize its answer in one to three short spoken \
sentences. Never read code, URLs, or long lists aloud; say the details are in the chat window.
- Small talk and questions about what Suzent is doing you may answer directly."""


def build_front_desk_agent(router: HandoffRouter) -> Agent:
    agent = Agent(instructions=FRONT_DESK_INSTRUCTIONS)

    async def delegate(request: str) -> str:
        """Hand the user's request to Suzent, which works on it in the chat window.

        Args:
            request: The user's request, restated clearly and completely.
        """
        return await router.delegate(request)

    async def cancel_task() -> str:
        """Stop the task Suzent is currently working on."""
        return await router.cancel_task()

    agent.tool_plain(delegate)
    agent.tool_plain(cancel_task)
    return agent


_NOISE = re.compile(r"<\s*(noise|unk|silence)\s*>", re.IGNORECASE)
_CJK = r"\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef"
_CJK_GAP = re.compile(rf"(?<=[{_CJK}])\s+(?=[{_CJK}])")
_CJK_PUNCT = {",": "，", ".": "。", "?": "？", "!": "！", ":": "：", ";": "；"}
# Gemini 3.1 also spaces it off: "怎么样 ? 要不要".
# Only sentence punctuation: followed by space, CJK or the end, so "3.8",
# "你好:)" and "好的..." are left alone.
_ASCII_PUNCT_AFTER_CJK = re.compile(
    rf"(?<=[\u4e00-\u9fff])\s*([,.?!:;])(?=\s|[{_CJK}A-Za-z]|$)\s*"
)


def normalize_transcript(text: str) -> str:
    """Clean provider transcripts for display: noise tags, CJK spacing, punctuation."""
    text = _NOISE.sub("", text or "")
    text = _ASCII_PUNCT_AFTER_CJK.sub(lambda m: _CJK_PUNCT[m.group(1)], text)
    text = _CJK_GAP.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


_STARTUP_LIMIT = 12000


def build_startup_context(messages: list[Any] | None) -> str:
    """The recent conversation, so the front desk knows what the chat is about."""
    from suzent.core.system_reminder import strip_system_reminders

    lines: list[str] = []
    size = 0
    for row in reversed(messages or []):
        if not isinstance(row, dict) or row.get("role") not in {"user", "assistant"}:
            continue
        content = row.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        text = strip_system_reminders(content).strip()
        if not text:
            continue
        text = text[:1500] + ("…" if len(text) > 1500 else "")
        line = f"{row['role']}: {text}"
        if size + len(line) > _STARTUP_LIMIT:
            break
        lines.append(line)
        size += len(line)
    if not lines:
        return ""
    body = "\n".join(reversed(lines))
    return (
        "[BACKEND] The conversation so far in this chat, for context only. "
        f"Do not reply to it.\n{body}"
    )


_MAX_CONTROL_BYTES = 4096

SessionFactory = Callable[[], AbstractAsyncContextManager[Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client_info(info: Any) -> dict[str, Any]:
    """Client diagnostics, reduced to a few short scalars before logging."""
    if not isinstance(info, dict):
        return {}
    clean: dict[str, Any] = {}
    for key, value in list(info.items())[:16]:
        if not isinstance(key, str) or len(key) > 40:
            continue
        if isinstance(value, str):
            clean[key] = value[:80]
        elif value is None or isinstance(value, (bool, int, float)):
            clean[key] = value
    return clean


def _cut_boundary(session: Any, bridge: "VoiceBridge") -> int:
    """Highest assistant part index that had started when the user cut in.

    The session knows which part is playing and which was last started even
    before any caption of it arrived (pydantic-ai private state; read
    defensively). The highest assistant index seen in captions backs it up.
    """

    def index(value: Any) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    candidates = [bridge._max_assistant_index]
    candidates.append(index(getattr(session, "_audio_part_index", None)))
    # pydantic-ai 2.64 keeps each response under way, with the index of the
    # part it last started, in the session core.
    responses = getattr(getattr(session, "_core", None), "_open_responses", None)
    if isinstance(responses, dict):
        for response in list(responses.values()):
            candidates.append(index(getattr(response, "open_part_index", None)))
    return max(value for value in candidates if value is not None)


class VoiceBridge:
    """Bridge one browser WebSocket to one realtime session bound to one chat.

    Server -> client state is inferred from signals every provider produces
    (transcripts, audio, turn completion), not from speech start/end events
    some providers never send. Whether Suzent is working is a separate flag.
    """

    def __init__(
        self,
        websocket: WebSocket,
        chat_id: str,
        *,
        session_factory: SessionFactory | None = None,
        model_id: str | None = None,
        router_options: dict[str, Any] | None = None,
        persist: Callable[[list[dict[str, Any]]], Any] | None = None,
        startup_messages: list[Any] | None = None,
    ) -> None:
        self.websocket = websocket
        self.chat_id = chat_id
        self._send_lock = asyncio.Lock()
        self._stopping = asyncio.Event()
        self._session_factory = session_factory
        self._model_id = model_id
        self._session: Any = None
        self._key = uuid.uuid4().hex[:8]
        self._state: str | None = None
        self._texts: dict[str, str] = {}
        self._finals: set[str] = set()
        self._delta_lines: list[tuple[str, str]] = []
        # Set when the model cannot cancel a reply: its remaining audio is dropped
        # here instead, until the user speaks again or the turn ends.
        self._muted = False
        # Transcripts of a reply cut off by that mute are dropped for good, even
        # if they arrive after the mute lifted (Gemini finalizes them late).
        # Part indices are session-unique and increasing, so every assistant
        # part started before the cut is at or below this; replies started
        # after it are above. (A user part's index is not a usable boundary:
        # it is claimed lazily, after the reply to it may have started.)
        self._max_assistant_index = -1
        self._cut_upto = -1
        # Audio has arrived since the last turn end: a reply is in progress.
        self._replying = False
        self._persist = persist or self._persist_to_db
        self._startup_messages = startup_messages
        self.router = HandoffRouter(
            chat_id,
            send_context=self._send_context,
            enqueue_spoken=self._enqueue_spoken,
            on_working=self._send_working,
            transcript_delta=self.take_transcript_delta,
            **(router_options or {}),
        )

    # -- outbound ------------------------------------------------------------------

    async def _send_json(self, message: dict[str, Any]) -> None:
        async with self._send_lock:
            await self.websocket.send_json(message)

    async def _send_bytes(self, chunk: bytes) -> None:
        async with self._send_lock:
            await self.websocket.send_bytes(chunk)

    async def _set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        await self._send_json({"type": "state", "state": state})

    async def _send_working(self, active: bool) -> None:
        await self._send_json({"type": "working", "active": active})

    async def _send_context(self, text: str) -> None:
        if self._session is not None:
            await self._session.send(text, respond=False)

    def _enqueue_spoken(self, text: str) -> None:
        if self._session is not None:
            self._session.enqueue(text, priority="when_idle")

    # -- transcripts -------------------------------------------------------------

    def take_transcript_delta(self) -> list[tuple[str, str]]:
        """(speaker, text) lines said since the last delegation, handed over once."""
        lines, self._delta_lines = self._delta_lines, []
        return lines

    def _delta_snapshot(self) -> list[tuple[str, str]]:
        """The delta as it stands, without consuming it (for a turn-end signal)."""
        return list(self._delta_lines)

    async def _on_transcript(
        self, index: int, speaker: str, raw: str, final: bool
    ) -> None:
        line_id = f"{self._key}:{index}"
        if speaker == "assistant":
            self._max_assistant_index = max(self._max_assistant_index, index)
            if self._muted or 0 <= index <= self._cut_upto:
                # The user cut this reply off and its audio is being dropped:
                # its words must not keep appearing in captions or the log.
                return
        text = normalize_transcript(raw)
        if not text:
            return
        if line_id in self._finals:
            # A finalized line only ever grows (a model's transcript can extend
            # after its part ended); a stale delta must not revert it.
            if len(text) <= len(self._texts.get(line_id, "")):
                return
            final = True
        self._texts[line_id] = text
        if speaker == "user":
            self._muted = False
        if speaker == "user" and not final:
            await self._set_state("user_speaking")
        await self._send_json(
            {
                "type": "transcript",
                "id": line_id,
                "speaker": speaker,
                "text": text,
                "final": final,
            }
        )
        if not final:
            return
        first = line_id not in self._finals
        self._finals.add(line_id)
        if first:
            self._delta_lines.append((speaker, text))
            if speaker == "user":
                self.router.note_user_utterance(line_id)
                await self._set_state("thinking")
        await self._save_line(line_id, speaker, text)

    async def _save_line(self, line_id: str, speaker: str, text: str) -> None:
        entry = {"id": line_id, "speaker": speaker, "text": text, "timestamp": _now()}
        try:
            result = self._persist([entry])
            if hasattr(result, "__await__"):
                await result
        except Exception as exc:
            logger.debug("Voice transcript could not be saved: {}", exc)

    async def _persist_to_db(self, entries: list[dict[str, Any]]) -> None:
        from suzent.database import get_database

        await asyncio.to_thread(get_database().append_voice_log, self.chat_id, entries)

    # -- session -----------------------------------------------------------------

    def _real_session_factory(self) -> SessionFactory:
        settings = get_voice_settings()
        model_id, model = resolve_realtime_model(settings)
        self._model_id = model_id
        logger.info(
            "Voice {} start: chat={} model={} language={} vad={}",
            self._key,
            self.chat_id,
            model_id,
            settings.realtime_language or "auto",
            (getattr(model, "settings", None) or {}).get("google_vad", "default"),
        )
        agent = build_front_desk_agent(self.router)
        return lambda: agent.realtime(model).session()

    def _load_startup_messages(self) -> list[Any]:
        if self._startup_messages is not None:
            return self._startup_messages
        from suzent.database import get_database

        chat = get_database().get_chat(self.chat_id)
        return list(chat.messages or []) if chat else []

    async def run(self) -> None:
        tasks: list[asyncio.Task[Any]] = []
        try:
            factory = self._session_factory or self._real_session_factory()
            async with factory() as session:
                self._session = session
                context = build_startup_context(
                    await asyncio.to_thread(self._load_startup_messages)
                )
                if context:
                    await session.send(context, respond=False)
                await self._send_json(
                    {
                        "type": "ready",
                        "chat_id": self.chat_id,
                        "input_sample_rate": session.audio_input_sample_rate,
                        "output_sample_rate": session.audio_output_sample_rate,
                        "model": self._model_id or "test",
                        "live_captions": _LIVE_CAPTIONS.get(self._model_id or ""),
                        "working": self.router.working or self.router._is_busy(),
                    }
                )
                self.router.start_watching()
                self.router.attach_if_busy()
                await self._set_state("listening")
                tasks = [
                    asyncio.create_task(self._mic_loop(session)),
                    asyncio.create_task(self._audio_loop(session)),
                    asyncio.create_task(self._event_loop(session)),
                    asyncio.create_task(self._transcript_loop(session)),
                ]
                stop_task = asyncio.create_task(self._stopping.wait())
                tasks.append(stop_task)  # cancelled and awaited in `finally`
                done, _pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
                if stop_task not in done:
                    for task in done:
                        if not task.cancelled() and (exc := task.exception()):
                            raise exc
        except WebSocketDisconnect:
            pass
        except RealtimeVoiceError as exc:
            await self._safe_error(exc.code, str(exc))
        except Exception as exc:
            logger.warning("Realtime voice session failed: {}", exc)
            await self._safe_error("session_error", str(exc))
        finally:
            # The delegated turn is an ordinary chat turn and outlives the call.
            self.router.close()
            self._session = None
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            try:
                await self._send_json({"type": "closed"})
            except Exception:
                pass
            try:
                await self.websocket.close()
            except Exception:
                pass

    async def _safe_error(self, code: str, message: str) -> None:
        try:
            await self._send_json({"type": "error", "code": code, "message": message})
        except Exception:
            pass

    async def _mic_loop(self, session: Any) -> None:
        while not self._stopping.is_set():
            message = await self.websocket.receive()
            if message.get("type") == "websocket.disconnect":
                self._stopping.set()
                return
            if data := message.get("bytes"):
                await session.send_audio(data)
                continue
            text = message.get("text")
            if not text or len(text) > _MAX_CONTROL_BYTES:
                continue
            try:
                control = json.loads(text)
            except ValueError:
                continue
            if not isinstance(control, dict):
                continue
            kind = control.get("type")
            if kind == "stop":
                self._stopping.set()
                return
            if kind == "interrupt":
                try:
                    played_ms = max(0, int(control.get("played_ms", 0)))
                except (TypeError, ValueError, OverflowError):
                    played_ms = 0
                await self._interrupt(session, played_ms)
            elif kind == "client_info":
                logger.info(
                    "Voice {} client: {}", self._key, _client_info(control.get("info"))
                )
            elif kind == "text":
                # Typed while the call is live: same route as speech.
                typed = str(control.get("text") or "").strip()
                if typed:
                    await self._on_transcript(
                        -len(self._finals) - 1, "user", typed, True
                    )
                    await session.send(typed)

    async def _interrupt(self, session: Any, played_ms: int) -> None:
        """Barge-in that never ends the call, whatever the model supports."""
        try:
            await session.interrupt(played_ms=played_ms)
            logger.info("Voice {} interrupt by client: truncated", self._key)
            return
        except UserError:
            pass  # No truncation (e.g. xAI): cancel without a playback position.
        try:
            await session.interrupt()
            logger.info("Voice {} interrupt by client: cancelled", self._key)
            return
        except UserError:
            pass  # No cancellation at all (e.g. Gemini Live): silence it locally.
        logger.info(
            "Voice {} interrupt by client: muted locally (replying={})",
            self._key,
            self._replying,
        )
        # Mute only a reply that is still arriving. A reply whose turn already
        # ended has nothing left to drop, and a mute set now would swallow the
        # next reply the model starts by itself (a spoken delegation result).
        self._muted = self._replying
        if self._muted:
            self._cut_upto = max(self._cut_upto, _cut_boundary(session, self))
        await self._send_json({"type": "interrupted"})
        await self._set_state("listening")

    async def _audio_loop(self, session: Any) -> None:
        async for chunk in session.stream_audio():
            self._replying = True
            if self._muted:
                continue
            await self._set_state("speaking")
            await self._send_bytes(chunk)

    async def _transcript_loop(self, session: Any) -> None:
        async for update in session.stream_transcripts(delta=True):
            await self._on_transcript(
                update.index, update.speaker, update.transcript, False
            )

    async def _event_loop(self, session: Any) -> None:
        async for event in session:
            if isinstance(event, PartEndEvent) and isinstance(event.part, SpeechPart):
                await self._on_transcript(
                    event.index,
                    event.part.speaker,
                    event.part.transcript or "",
                    True,
                )
            elif isinstance(event, RealtimeInputSpeechStartEvent):
                if self._replying:
                    # The provider heard "the user" over its own reply: a real
                    # barge-in, or its voice echoing back through the mic.
                    logger.info("Voice {} speech start during reply", self._key)
                self._muted = False
                await self._set_state("user_speaking")
            elif isinstance(event, RealtimeInputSpeechEndEvent):
                await self._set_state("thinking")
            elif isinstance(
                event, (RealtimeOutputSpeechEndEvent, RealtimeTurnCompleteEvent)
            ):
                self.router.note_front_desk_turn_end(self._delta_snapshot())
                self._muted = self._replying = False
                await self._set_state("listening")
            elif isinstance(event, RealtimeResponseInterruptedEvent):
                logger.info("Voice {} reply interrupted by provider VAD", self._key)
                self.router.note_front_desk_turn_end(self._delta_snapshot())
                self._muted = self._replying = False
                await self._send_json({"type": "interrupted"})
                await self._set_state("listening")
            elif isinstance(event, RealtimeSessionErrorEvent):
                await self._safe_error("session_error", event.message)
                if not getattr(event, "recoverable", False):
                    self._stopping.set()
