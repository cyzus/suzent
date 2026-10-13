"""Batch memory extraction over each chat's JSONL transcript.

Extracting after every turn sees too little at once: a plan stated in one turn and
revised two turns later is stored twice, and most turns hold nothing worth keeping.
Instead the transcript is the queue. Each chat keeps a cursor -- how many transcript
entries have been extracted -- and the turns past it are extracted together once
enough have built up, once the chat goes quiet, before its context is compacted, or
on the next start if the app closed first.

The cursor only moves after a batch is written, so a failed batch is retried rather
than lost.
"""

import asyncio
import json
import os
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
# Per-message cap inside a batch.
MESSAGE_CHARS = 4000

CURSORS_FILE = "memory_cursors.json"

type Entry = dict[str, Any]


def _turns(entries: list[Entry]) -> list[list[Entry]]:
    """Group transcript entries into turns, each opening at a user entry."""
    turns: list[list[Entry]] = []
    for entry in entries:
        if entry.get("role") == "user" or not turns:
            turns.append([entry])
        else:
            turns[-1].append(entry)
    return turns


def _entry_chars(entry: Entry) -> int:
    return len(str(entry.get("content", "")))


def _format_turn(turn: list[Entry]) -> str:
    lines: list[str] = []
    try:
        stamp = format_local_date(datetime.fromisoformat(turn[0]["ts"]))
        lines.append(f"### Turn on {stamp}")
    except (KeyError, TypeError, ValueError):
        lines.append("### Turn")
    for entry in turn:
        content = str(entry.get("content", ""))[:MESSAGE_CHARS]
        if entry.get("role") == "user":
            lines.append(f"USER: {content}")
            continue
        for action in entry.get("actions") or []:
            output = action.get("output")
            result = f" -> {output}" if output else ""
            lines.append(f"ACTION: {action.get('tool')}({action.get('args')}){result}")
        lines.append(f"ASSISTANT: {content}")
    return "\n".join(lines)


def format_batch(context: list[list[Entry]], new: list[list[Entry]]) -> str:
    """Render a batch for the extractor: earlier context first, then new turns."""
    parts: list[str] = []
    if context:
        parts.append("## Earlier context (already processed; do not extract)")
        parts.extend(_format_turn(t) for t in context)
    parts.append("## New turns")
    parts.extend(_format_turn(t) for t in new)
    return "\n\n".join(parts)


class ExtractionQueue:
    """Decides when each chat's pending transcript turns are extracted."""

    def __init__(self, transcripts_dir: Optional[Path] = None) -> None:
        self._dir = transcripts_dir
        self._cursor_lock = asyncio.Lock()
        self._timers: dict[str, asyncio.Task] = {}

    @property
    def transcripts_dir(self) -> Path:
        if self._dir is None:
            from suzent.session.transcript import TranscriptManager

            self._dir = TranscriptManager().base_dir
        return self._dir

    # --- cursors ---

    def _cursors_path(self) -> Path:
        return self.transcripts_dir / CURSORS_FILE

    def _read_cursors(self) -> Optional[dict[str, int]]:
        try:
            return json.loads(self._cursors_path().read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as e:
            # Rebuilt as on a first run: losing a few pending turns beats
            # re-extracting every chat from the beginning.
            logger.warning(f"Unreadable memory cursors; rebuilding them: {e}")
            return None

    def _write_cursors(self, cursors: dict[str, int]) -> None:
        path = self._cursors_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cursors, indent=0), encoding="utf-8")
        os.replace(tmp, path)

    async def _load_cursors(self) -> dict[str, int]:
        """Read the cursors, creating them on the first run. Call under the lock.

        The first run after upgrading from per-turn extraction finds no cursor file.
        Everything already in the transcripts was extracted turn by turn, so every
        existing chat starts at its current end instead of being re-extracted.
        """
        cursors = self._read_cursors()
        if cursors is None:
            cursors = {
                path.stem: len(await self._read_entries(path.stem))
                for path in self.transcripts_dir.glob("*.jsonl")
            }
            self._write_cursors(cursors)
        return cursors

    async def _cursor(self, chat_id: str) -> int:
        async with self._cursor_lock:
            return (await self._load_cursors()).get(chat_id, 0)

    async def _advance(self, chat_id: str, cursor: int) -> None:
        async with self._cursor_lock:
            cursors = await self._load_cursors()
            cursors[chat_id] = cursor
            self._write_cursors(cursors)

    async def _read_entries(self, chat_id: str) -> list[Entry]:
        from suzent.session.transcript import TranscriptManager

        return await TranscriptManager(str(self.transcripts_dir)).read_transcript(
            chat_id
        )

    # --- triggers ---

    async def note_turn(self, chat_id: str, user_id: str) -> None:
        """Called after a turn reaches the transcript."""
        entries = await self._read_entries(chat_id)
        pending = entries[await self._cursor(chat_id) :]
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
        """Mark everything in the transcript as handled without extracting it."""
        self._cancel_timer(chat_id)
        await self._advance(chat_id, len(await self._read_entries(chat_id)))

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
        try:
            while True:
                # One batch per hold of the chat's memory lock, so a long backlog
                # does not run into the per-task timeout.
                async with memory_task(chat_id):
                    entries = await self._read_entries(chat_id)
                    cursor = await self._cursor(chat_id)
                    pending = _turns(entries[cursor:])
                    # The assistant half of the newest turn may not be written yet.
                    if pending and pending[-1][-1].get("role") == "user":
                        pending.pop()
                    if not pending:
                        break
                    batch = self._split(pending)[0]
                    context = _turns(entries[:cursor])[-CONTEXT_TURNS:]
                    await memory_mgr.process_conversation_for_memories(
                        format_batch(context, batch),
                        chat_id=chat_id,
                        user_id=user_id,
                        recall_query=format_batch([], batch),
                    )
                    await self._advance(
                        chat_id, cursor + sum(len(turn) for turn in batch)
                    )
                    done += len(batch)
        except Exception as e:
            logger.warning(f"Memory extraction for {chat_id} stopped early: {e}")
        if done:
            logger.info(f"Extracted memories from {done} turn(s) of chat {chat_id}")
        return done

    @staticmethod
    def _split(turns: list[list[Entry]]) -> list[list[list[Entry]]]:
        batches: list[list[list[Entry]]] = []
        size = MAX_BATCH_CHARS
        for turn in turns:
            chars = sum(_entry_chars(e) for e in turn)
            if size + chars > MAX_BATCH_CHARS:
                batches.append([])
                size = 0
            batches[-1].append(turn)
            size += chars
        return batches

    async def catch_up(self, user_id: str) -> None:
        """On start, extract what was pending when the app last closed."""
        async with self._cursor_lock:
            cursors = await self._load_cursors()
        for path in sorted(self.transcripts_dir.glob("*.jsonl")):
            if len(await self._read_entries(path.stem)) > cursors.get(path.stem, 0):
                await self.flush(path.stem, user_id)

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
