"""Batch memory extraction over each chat's event log.

Extracting after every turn sees too little at once: a plan stated in one turn and
revised two turns later is stored twice, and most turns hold nothing worth keeping.
Instead the chat log is the queue. Each chat keeps a cursor -- the position of the
last message extracted -- and the messages past it are extracted together once
enough have built up, once the chat goes quiet, before its context is compacted, or
on the next start if the app closed first.

The cursor only moves after a batch is written, so a failed batch is retried rather
than lost.
"""

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from suzent.logger import get_logger
from suzent.memory.memory_context import format_local_date

logger = get_logger(__name__)

# Extract as soon as this much is pending...
BATCH_TURNS = 6
BATCH_CHARS = 8000
# ...otherwise once the chat has been quiet this long.
IDLE_SECONDS = 600
# One extraction call never covers more than this; a longer backlog is split.
MAX_BATCH_CHARS = 16000
# Already-extracted turns shown ahead of a batch so it does not start mid-topic.
CONTEXT_TURNS = 2
# Caps inside a batch: tool arguments can be whole files.
MESSAGE_CHARS = 4000
ACTION_CHARS = 300
TURN_CHARS = 8000
CONTEXT_TURN_CHARS = 2000

CURSORS_FILE = ".memory_cursors.json"
# Turns in these chats are the app's own housekeeping, never the user's.
SYSTEM_PLATFORMS = ("dream", "subagent", "subagent_wakeup")

type Entry = dict[str, Any]
# (event seq, index within that event): a splice inserts many messages at one seq.
type Position = tuple[int, int]

START: Position = (0, 0)

_REASONING_RE = re.compile(
    r"<details\s+data-reasoning=[\"']true[\"'][^>]*>.*?</details>\s*",
    re.IGNORECASE | re.DOTALL,
)


def _turns(entries: list[Entry]) -> list[list[Entry]]:
    """Group entries into turns, each opening at a user entry."""
    turns: list[list[Entry]] = []
    for entry in entries:
        if entry.get("role") == "user" or not turns:
            turns.append([entry])
        else:
            turns[-1].append(entry)
    return turns


def _is_scheduled(turn: list[Entry]) -> bool:
    """A turn a scheduled task started, not the user.

    Its prompt is the task's spec, which capture must never store as something the
    user said.
    """
    first = turn[0]
    return first.get("role") == "user" and bool(first.get("scheduled"))


def _entry_chars(entry: Entry) -> int:
    return len(str(entry.get("content", "")))


def _clip(text: object, limit: int) -> str:
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "..."


def _format_turn(turn: list[Entry]) -> str:
    lines: list[str] = []
    try:
        stamp = format_local_date(datetime.fromisoformat(turn[0]["ts"]))
        lines.append(f"### Turn on {stamp}")
    except (KeyError, TypeError, ValueError):
        lines.append("### Turn")
    for entry in turn:
        content = _clip(entry.get("content", ""), MESSAGE_CHARS)
        if entry.get("role") == "user":
            lines.append(f"USER: {content}")
            continue
        for action in entry.get("actions") or []:
            args = _clip(action.get("args"), ACTION_CHARS)
            output = action.get("output")
            result = f" -> {_clip(output, ACTION_CHARS)}" if output else ""
            lines.append(f"ACTION: {action.get('tool')}({args}){result}")
        lines.append(f"ASSISTANT: {content}")
    return _clip("\n".join(lines), TURN_CHARS)


def format_batch(context: list[list[Entry]], new: list[list[Entry]]) -> str:
    """Render a batch for the extractor: earlier context first, then new turns."""
    parts: list[str] = []
    if context:
        parts.append("## Earlier context (already processed; do not extract)")
        parts.extend(_clip(_format_turn(t), CONTEXT_TURN_CHARS) for t in context)
    parts.append("## New turns")
    parts.extend(_format_turn(t) for t in new)
    return "\n\n".join(parts)


def _message_text(message: dict[str, Any]) -> str:
    """The visible reply: text parts, without the reasoning folded into content."""
    texts = [
        str(part.get("text") or "")
        for part in message.get("parts") or []
        if isinstance(part, dict) and part.get("type") == "text"
    ]
    if any(texts):
        return "\n".join(t for t in texts if t).strip()
    return _REASONING_RE.sub("", str(message.get("content") or "")).strip()


def _actions(message: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for part in message.get("parts") or []:
        if not isinstance(part, dict) or part.get("type") != "tool":
            continue
        args: Any = part.get("args")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                pass
        output = part.get("output")
        actions.append(
            {
                "tool": part.get("toolName"),
                "args": args,
                "output": str(output)[:200] if output else "",
            }
        )
    return actions


def to_entry(message: Any, position: Position, ts: Optional[str]) -> Optional[Entry]:
    """Turn a display message into what extraction reads, or None to skip it."""
    from suzent.core.system_reminder import strip_system_reminders

    if not isinstance(message, dict):
        return None
    base = {"pos": position, "ts": message.get("timestamp") or ts}
    match message.get("role"):
        case "user":
            # The hidden reminder carries recalled memories the extractor would
            # store again.
            content = strip_system_reminders(str(message.get("content") or ""))
            return {**base, "role": "user", "content": content}
        case "system_triggered":
            content = str(message.get("content") or "")
            return {**base, "role": "user", "content": content, "scheduled": True}
        case "assistant":
            return {
                **base,
                "role": "assistant",
                "content": _message_text(message),
                "actions": _actions(message),
            }
    return None


def _message_key(message: Any) -> str:
    if not isinstance(message, dict):
        return repr(message)
    return f"{message.get('role')}\0{message.get('content')}"


def _legacy_pending_turns() -> dict[str, int]:
    """Turns the old transcript-based queue had not extracted yet, per chat.

    That queue counted extracted entries in a transcript copy of each chat; the
    copies are no longer written, so its backlog is carried over as a number of
    trailing turns.
    """
    from suzent.config import DATA_DIR

    folder = DATA_DIR / "transcripts"
    try:
        cursors = json.loads((folder / "memory_cursors.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    pending: dict[str, int] = {}
    for path in folder.glob("*.jsonl"):
        try:
            lines = path.read_text("utf-8").splitlines()
        except OSError:
            continue
        waiting = 0
        for line in lines[int(cursors.get(path.stem, 0)) :]:
            try:
                waiting += json.loads(line).get("role") == "user"
            except (ValueError, AttributeError):
                continue
        if waiting:
            pending[path.stem] = waiting
    return pending


class ChatLogView:
    """A chat's current messages, each tagged with the log position that added it."""

    def __init__(self) -> None:
        self.messages: list[tuple[Position, Any, Optional[str]]] = []
        self.platform: Optional[str] = None
        self.last: Position = START

    def apply(self, event: dict[str, Any]) -> None:
        seq, kind, data, ts = event["seq"], event["type"], event["data"], event["ts"]
        match kind:
            case "chat.created" | "chat.imported":
                self.platform = (data.get("config") or {}).get("platform")
                self.messages = [
                    ((seq, i), m, ts) for i, m in enumerate(data.get("messages") or [])
                ]
            case "chat.deleted":
                self.messages = []
            case "config.merge":
                if "platform" in data.get("set", {}):
                    self.platform = data["set"]["platform"]
                elif "platform" in data.get("unset", []):
                    self.platform = None
            case "message.append":
                self.messages.append(((seq, 0), data, ts))
            case "messages.splice":
                start, delete = data["start"], data["delete"]
                # A rewrite that keeps a message unchanged in substance (a
                # compaction merge, a filled-in timestamp) must not make it new.
                removed: dict[str, list[Position]] = {}
                for position, message, _ in self.messages[start : start + delete]:
                    removed.setdefault(_message_key(message), []).append(position)
                inserted = []
                for i, message in enumerate(data["insert"]):
                    kept = removed.get(_message_key(message))
                    position = kept.pop(0) if kept else (seq, i)
                    inserted.append((position, message, ts))
                self.messages[start : start + delete] = inserted
        self.last = (seq, 1 << 30)

    def entries(self) -> list[Entry]:
        return [
            entry
            for position, message, ts in self.messages
            if (entry := to_entry(message, position, ts)) is not None
        ]


class ExtractionQueue:
    """Decides when each chat's pending turns are extracted."""

    def __init__(self, chat_log: Any = None, cursors_path: Optional[Path] = None):
        self._log = chat_log
        self._cursors_file = cursors_path
        self._cursor_lock = asyncio.Lock()
        self._timers: dict[str, asyncio.Task] = {}

    @property
    def chat_log(self) -> Any:
        if self._log is None:
            from suzent.database import get_database

            self._log = get_database().chat_log
        return self._log

    # --- reading ---

    def _view_sync(self, chat_id: str) -> ChatLogView:
        view = ChatLogView()
        for event in self.chat_log.events(chat_id):
            view.apply(event)
        return view

    async def _view(self, chat_id: str) -> ChatLogView:
        return await asyncio.to_thread(self._view_sync, chat_id)

    # --- cursors ---

    def _cursors_path(self) -> Path:
        return self._cursors_file or Path(self.chat_log.root) / CURSORS_FILE

    def _read_cursors(self) -> Optional[dict[str, Position]]:
        try:
            raw = json.loads(self._cursors_path().read_text(encoding="utf-8"))
            return {chat_id: (int(c[0]), int(c[1])) for chat_id, c in raw.items()}
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError, IndexError, AttributeError) as e:
            # Rebuilt as on a first run: losing a few pending turns beats
            # re-extracting every chat from the beginning.
            logger.warning(f"Unreadable memory cursors; rebuilding them: {e}")
            return None

    def _write_cursors(self, cursors: dict[str, Position]) -> None:
        path = self._cursors_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({k: list(v) for k, v in cursors.items()}, indent=0),
            encoding="utf-8",
        )
        os.replace(tmp, path)

    async def _load_cursors(self) -> dict[str, Position]:
        """Read the cursors, creating them on the first run. Call under the lock.

        With no cursor file every existing chat starts at its current end, except
        for the turns the old transcript-based queue still had pending.
        """
        cursors = self._read_cursors()
        if cursors is None:
            pending = await asyncio.to_thread(_legacy_pending_turns)
            cursors = {}
            for chat_id in self.chat_log.chat_ids():
                view = await self._view(chat_id)
                cursors[chat_id] = view.last
                turns = _turns(view.entries())
                waiting = pending.get(chat_id, 0)
                if waiting and turns:
                    earlier = turns[: max(len(turns) - waiting, 0)]
                    cursors[chat_id] = (
                        max(e["pos"] for t in earlier for e in t) if earlier else START
                    )
            self._write_cursors(cursors)
        return cursors

    async def _cursor(self, chat_id: str) -> Position:
        async with self._cursor_lock:
            return (await self._load_cursors()).get(chat_id, START)

    async def _advance(self, chat_id: str, cursor: Position) -> None:
        async with self._cursor_lock:
            cursors = await self._load_cursors()
            cursors[chat_id] = cursor
            self._write_cursors(cursors)

    # --- triggers ---

    async def note_turn(self, chat_id: str, user_id: str) -> None:
        """Called after a turn reaches the chat log."""
        view = await self._view(chat_id)
        if view.platform in SYSTEM_PLATFORMS:
            return
        cursor = await self._cursor(chat_id)
        pending = [e for e in view.entries() if e["pos"] > cursor]
        if not pending:
            return
        enough = len(_turns(pending)) >= BATCH_TURNS or (
            sum(_entry_chars(e) for e in pending) >= BATCH_CHARS
        )
        if enough:
            self._cancel_timer(chat_id)
            await self.flush(chat_id, user_id)
        else:
            self._arm_timer(chat_id, user_id)

    async def skip_pending(self, chat_id: str) -> None:
        """Mark everything in the chat log as handled without extracting it."""
        from suzent.core.memory_tasks import memory_task

        self._cancel_timer(chat_id)
        # Under the chat's memory lock, so a batch still in flight cannot write
        # its older cursor over this one afterwards.
        async with memory_task(chat_id):
            await self._advance(chat_id, (await self._view(chat_id)).last)

    def _arm_timer(self, chat_id: str, user_id: str) -> None:
        self._cancel_timer(chat_id)

        async def _wait_then_flush() -> None:
            await asyncio.sleep(IDLE_SECONDS)
            self._timers.pop(chat_id, None)
            await self.flush(chat_id, user_id)

        self._timers[chat_id] = asyncio.create_task(
            _wait_then_flush(), name=f"memory_idle_{chat_id}"
        )

    def _cancel_timer(self, chat_id: str) -> None:
        timer = self._timers.pop(chat_id, None)
        if timer and timer is not asyncio.current_task():
            timer.cancel()

    async def flush(self, chat_id: str, user_id: str) -> int:
        """Extract every pending turn of *chat_id*. Returns how many were done."""
        from suzent.core.memory_tasks import memory_task
        from suzent.memory.lifecycle import get_memory_manager

        memory_mgr = get_memory_manager()
        if not memory_mgr:
            return 0

        self._cancel_timer(chat_id)
        done = 0
        # Only what was there when the flush began; later turns get their own
        # trigger, and may have been said with memory switched off.
        end: Optional[Position] = None
        try:
            while True:
                # One batch per hold of the chat's memory lock, so a long backlog
                # does not run into the per-task timeout.
                async with memory_task(chat_id):
                    view = await self._view(chat_id)
                    if view.platform in SYSTEM_PLATFORMS:
                        break
                    if end is None:
                        end = view.last
                    cursor = await self._cursor(chat_id)
                    entries = view.entries()
                    pending = _turns([e for e in entries if cursor < e["pos"] <= end])
                    # The assistant half of the newest turn may not be written yet.
                    if pending and pending[-1][-1].get("role") == "user":
                        pending.pop()
                    if not pending:
                        break
                    done_entries = [e for e in entries if e["pos"] <= cursor]
                    context = [t for t in _turns(done_entries) if not _is_scheduled(t)][
                        -CONTEXT_TURNS:
                    ]
                    budget = MAX_BATCH_CHARS - len(format_batch(context, []))
                    batch = self._split(pending, budget)[0]
                    # Scheduled turns never reach user-fact capture, but their
                    # failures and fixes are lessons like any other.
                    new = [t for t in batch if not _is_scheduled(t)]
                    if new:
                        await memory_mgr.process_conversation_for_memories(
                            format_batch(context, new),
                            chat_id=chat_id,
                            user_id=user_id,
                            recall_query=format_batch([], new),
                        )
                    await memory_mgr.process_experience(
                        format_batch(context, batch), chat_id=chat_id, user_id=user_id
                    )
                    await self._advance(
                        chat_id, max(e["pos"] for turn in batch for e in turn)
                    )
                    done += len(batch)
        except Exception as e:
            logger.warning(f"Memory extraction for {chat_id} stopped early: {e}")
        if done:
            logger.info(f"Extracted memories from {done} turn(s) of chat {chat_id}")
        return done

    @staticmethod
    def _split(turns: list[list[Entry]], budget: int) -> list[list[list[Entry]]]:
        """Group turns into batches whose rendered size fits *budget*.

        A turn renders to at most TURN_CHARS, so every batch holds at least one.
        """
        batches: list[list[list[Entry]]] = []
        size = 0
        for turn in turns:
            chars = len(_format_turn(turn))
            if not batches or size + chars > budget:
                batches.append([])
                size = 0
            batches[-1].append(turn)
            size += chars
        return batches

    async def catch_up(self, user_id: str) -> None:
        """On start, extract what was pending when the app last closed."""
        async with self._cursor_lock:
            cursors = await self._load_cursors()
        for chat_id in self.chat_log.chat_ids():
            view = await self._view(chat_id)
            if view.platform in SYSTEM_PLATFORMS:
                continue
            cursor = cursors.get(chat_id, START)
            if any(e["pos"] > cursor for e in view.entries()):
                await self.flush(chat_id, user_id)

    async def shutdown(self) -> None:
        timers = list(self._timers.values())
        self._timers.clear()
        for timer in timers:
            timer.cancel()
        await asyncio.gather(*timers, return_exceptions=True)


_queue: Optional[ExtractionQueue] = None


def get_extraction_queue() -> ExtractionQueue:
    global _queue
    if _queue is None:
        _queue = ExtractionQueue()
    return _queue
