"""The turn being streamed right now, kept out of SQLite until it is finished.

A streaming reply used to be rewritten into the chat row every 0.75s as a
``_streaming_draft`` message. Each of those writes re-serialized the whole
conversation and took the SQLite write lock, so every other write in the app
(mailbox, other chats, settings) queued behind the token stream.

Now the live turn lives in two places:

* an in-memory overlay that ``GET /chat`` merges into the persisted messages,
  so a reload mid-turn still shows the reply so far;
* an append-only journal, ``<chat log root>/.live/<chat>.<run>.jsonl``, that
  records each part as it changes. It is flushed on every write and fsynced
  when the turn ends. It exists only so a crash mid-turn does not lose what
  the user already saw: on the next start the journal is folded back into an
  assistant message (marked interrupted when the turn never finished) and
  written to the chat like any finished reply.

When the turn's real write lands, the overlay is dropped and the journal
deleted. The journal never touches SQLite, and one writer thread serves every
chat, so writes to a file never interleave.

Journal lines are ``{"v": 1, "ts": ..., "type": ..., "data": ...}``:

* ``turn.started`` ``{chat_id, run_id, started_at, model}``
* ``turn.part`` ``{index, part}``: the full part at that index, replacing any
  earlier line for the same index
* ``turn.finished`` ``{finished_at}``
"""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import IO, Any, Optional
from urllib.parse import quote

from suzent.logger import get_logger

logger = get_logger(__name__)

JOURNAL_VERSION = 1
LIVE_FOLDER = ".live"
INTERRUPTED_OUTPUT = "Interrupted: Suzent stopped before this finished"


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _line(kind: str, data: Any) -> str:
    return (
        json.dumps(
            {"v": JOURNAL_VERSION, "ts": _now(), "type": kind, "data": data},
            ensure_ascii=False,
        )
        + "\n"
    )


def message_content(parts: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        text
        for part in parts
        if part.get("type") == "text" and (text := str(part.get("text") or "").strip())
    )


@dataclass
class _OpenJournal:
    handle: IO[str]
    parts: list[str] = field(default_factory=list)


@dataclass
class FoldedTurn:
    """What a journal says about one run."""

    chat_id: str
    run_id: str
    started_at: Optional[str]
    model: Optional[str]
    parts: list[dict[str, Any]]
    finished_at: Optional[str]
    last_ts: Optional[str]

    def message(self) -> dict[str, Any]:
        """The assistant row this run shows as, closing any work left open."""
        parts = deepcopy(self.parts)
        if self.finished_at is None:
            for part in parts:
                if part.get("type") == "tool" and part.get("state") in {
                    "running",
                    "approval-requested",
                }:
                    part["state"] = "error"
                    part["approvalId"] = None
                    part["output"] = part.get("output") or INTERRUPTED_OUTPUT
                    part["outcome"] = "interrupted"
        finished_at = self.finished_at or self.last_ts
        return {
            "role": "assistant",
            "content": message_content(parts),
            "parts": parts,
            "_streaming_run_id": self.run_id,
            "id": self.run_id,
            **(
                {"timestamp": self.started_at, "run_started_at": self.started_at}
                if self.started_at
                else {}
            ),
            **({"run_finished_at": finished_at} if finished_at else {}),
            **({"interrupted": True} if self.finished_at is None else {}),
            "model": self.model,
        }


def fold_journal(path: Path) -> Optional[FoldedTurn]:
    """Read a journal back, stopping at a torn or unreadable line."""
    header: Optional[dict[str, Any]] = None
    parts: dict[int, dict[str, Any]] = {}
    finished_at: Optional[str] = None
    last_ts: Optional[str] = None
    try:
        # Bytes, not text: a crash can tear a line inside a multibyte character,
        # and decoding it eagerly would lose the whole journal.
        with path.open("rb") as handle:
            for raw in handle:
                if not raw.endswith(b"\n"):
                    break
                try:
                    event = json.loads(raw.decode("utf-8"))
                except ValueError:
                    break
                if not isinstance(event, dict) or event.get("v") != JOURNAL_VERSION:
                    break
                data = event.get("data")
                kind = event.get("type")
                last_ts = event.get("ts") or last_ts
                if kind == "turn.started" and isinstance(data, dict):
                    header = data
                elif kind == "turn.part" and isinstance(data, dict):
                    index, part = data.get("index"), data.get("part")
                    if isinstance(index, int) and isinstance(part, dict):
                        parts[index] = part
                elif kind == "turn.finished" and isinstance(data, dict):
                    finished_at = data.get("finished_at") or event.get("ts")
    except OSError as exc:
        logger.warning(f"Could not read live turn journal {path.name}: {exc}")
        return None
    if not header or not header.get("chat_id") or not header.get("run_id"):
        return None
    return FoldedTurn(
        chat_id=str(header["chat_id"]),
        run_id=str(header["run_id"]),
        started_at=header.get("started_at"),
        model=header.get("model"),
        parts=[parts[index] for index in sorted(parts)],
        finished_at=finished_at,
        last_ts=last_ts,
    )


class LiveTurns:
    """Overlays and journals for every turn currently streaming."""

    def __init__(self, log_root: Path) -> None:
        self.folder = Path(log_root) / LIVE_FOLDER
        # One thread, so lines for a run are written in the order submitted.
        self._writer = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="live-turn-journal"
        )
        self._open: dict[Path, _OpenJournal] = {}
        self._overlays: dict[str, dict[str, Any]] = {}
        self._overlay_lock = threading.Lock()

    def path(self, chat_id: str, run_id: str) -> Path:
        return self.folder / f"{quote(chat_id, safe='')}.{quote(run_id, safe='')}.jsonl"

    def publish(self, chat_id: str, message: dict[str, Any]) -> None:
        with self._overlay_lock:
            self._overlays[chat_id] = message

    def overlay(self, chat_id: str) -> Optional[dict[str, Any]]:
        with self._overlay_lock:
            return self._overlays.get(chat_id)

    def retract(self, chat_id: str, run_id: str) -> None:
        with self._overlay_lock:
            current = self._overlays.get(chat_id)
            if current is not None and current.get("_streaming_run_id") == run_id:
                del self._overlays[chat_id]

    def record(
        self,
        chat_id: str,
        run_id: str,
        parts: list[dict[str, Any]],
        *,
        started_at: str,
        model: Optional[str],
    ) -> Future[None]:
        """Append the parts that changed since the last record of this run."""
        header = {
            "chat_id": chat_id,
            "run_id": run_id,
            "started_at": started_at,
            "model": model,
        }
        return self._writer.submit(
            self._record, self.path(chat_id, run_id), header, parts
        )

    def finish(self, chat_id: str, run_id: str, finished_at: str) -> Future[None]:
        """Mark the run finished and make the journal durable."""
        return self._writer.submit(
            self._finish, self.path(chat_id, run_id), finished_at
        )

    def discard(self, chat_id: str, run_id: str) -> Future[None]:
        return self._writer.submit(self._discard, self.path(chat_id, run_id))

    def journals(self) -> list[Path]:
        if not self.folder.is_dir():
            return []
        return sorted(path for path in self.folder.glob("*.jsonl") if path.is_file())

    def _record(
        self, path: Path, header: dict[str, Any], parts: list[dict[str, Any]]
    ) -> None:
        journal = self._open.get(path)
        lines: list[str] = []
        if journal is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            journal = _OpenJournal(handle=path.open("a", encoding="utf-8"))
            self._open[path] = journal
            lines.append(_line("turn.started", header))
        for index, part in enumerate(parts):
            encoded = json.dumps(part, ensure_ascii=False, sort_keys=True)
            if index < len(journal.parts) and journal.parts[index] == encoded:
                continue
            lines.append(_line("turn.part", {"index": index, "part": part}))
            if index < len(journal.parts):
                journal.parts[index] = encoded
            else:
                journal.parts.append(encoded)
        if lines:
            journal.handle.write("".join(lines))
            journal.handle.flush()

    def _finish(self, path: Path, finished_at: str) -> None:
        journal = self._open.pop(path, None)
        if journal is None:
            return
        try:
            journal.handle.write(_line("turn.finished", {"finished_at": finished_at}))
            journal.handle.flush()
            os.fsync(journal.handle.fileno())
        finally:
            journal.handle.close()

    def _discard(self, path: Path) -> None:
        journal = self._open.pop(path, None)
        if journal is not None:
            journal.handle.close()
        path.unlink(missing_ok=True)

    def recover(self, db: Any, path: Path) -> bool:
        """Write a leftover journal's run into its chat, then delete the journal.

        Returns whether a message was written. A run whose finished row is
        already in the chat is left alone; so is a chat that no longer exists.
        """
        if self._open.get(path) is not None or not path.exists():
            return False
        turn = fold_journal(path)
        written = False
        if turn is not None and turn.parts:
            chat = db.get_chat(turn.chat_id)
            already_final = chat is not None and any(
                isinstance(row, dict)
                and row.get("_streaming_run_id") == turn.run_id
                and not row.get("_streaming_draft")
                for row in chat.messages or []
            )
            if chat is not None and not already_final:
                written = bool(
                    db.merge_streamed_display_message(turn.chat_id, turn.message())
                )
                if written:
                    logger.info(
                        f"Recovered {'interrupted' if turn.finished_at is None else 'unsaved'} "
                        f"reply for chat {turn.chat_id} from its live journal"
                    )
        path.unlink(missing_ok=True)
        return written

    def settle(
        self, db: Any, chat_id: str, run_id: str, *, landed: bool, last_chance: bool
    ) -> None:
        """Retire a run once its reply is in the chat (blocking).

        *landed* says the turn's write already committed the reply. Otherwise,
        with *last_chance*, the journal's copy is written back now, since
        nothing after this point would write it; without it the overlay and
        journal stay for the write still to come.
        """
        if landed:
            self.discard(chat_id, run_id).result()
        elif last_chance:
            self.recover(db, self.path(chat_id, run_id))
        else:
            return
        self.retract(chat_id, run_id)

    def recover_all(self, db: Any) -> int:
        recovered = 0
        for path in self.journals():
            try:
                recovered += self.recover(db, path)
            except Exception as exc:
                logger.warning(f"Could not recover live turn {path.name}: {exc}")
        return recovered


_live_turns: Optional[LiveTurns] = None
_live_turns_lock = threading.Lock()


def get_live_turns() -> LiveTurns:
    """The process-wide registry, rooted next to the chat logs."""
    global _live_turns
    from suzent.database import get_database

    root = Path(get_database().chat_log.root)
    with _live_turns_lock:
        if _live_turns is None or _live_turns.folder.parent != root:
            _live_turns = LiveTurns(root)
        return _live_turns


async def settle_turn(
    chat_id: str, run_id: str, *, landed: bool, last_chance: bool = False
) -> None:
    """Async wrapper for :meth:`LiveTurns.settle`; never raises."""
    import asyncio

    from suzent.database import get_database

    try:
        live = get_live_turns()
        await asyncio.to_thread(
            live.settle,
            get_database(),
            chat_id,
            run_id,
            landed=landed,
            last_chance=last_chance,
        )
    except Exception as exc:
        logger.warning(f"Could not settle live turn {run_id} of {chat_id}: {exc}")
