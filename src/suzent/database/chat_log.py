"""Append-only JSONL event log for each chat: the source of truth for chats.

Each chat gets ``<root>/<chat_id>.jsonl``. Every line is one event:

    {"v": 1, "seq": 7, "ts": "...", "type": "message.append", "data": {...}}

Folding a chat's events with :func:`apply_event` yields its *projection*: the
durable parts of the ``chats`` row in a JSON-only form (see :func:`project_chat`),
plus the chat's retry checkpoint, which has no row of its own. The log records
only differences between successive projections, so its size grows with the
conversation rather than with the number of writes.

Writes go to the log first. The database layer applies a write to SQLite
without committing, projects the uncommitted row, and :meth:`ChatEventLog.prepare`
appends and fsyncs whatever changed. Only then does SQLite commit; if the commit
fails the append is truncated away. A crash between the two leaves the log
ahead of SQLite, and the next start replays it into the row. ``chats.db`` is
therefore an index that can be rebuilt from the logs at any time.

Strings of 64 KiB or more (pasted images, large tool output) are stored once
under ``<root>/.media/<sha256>`` and referenced as ``{"$media": "<sha256>"}``,
which keeps the logs small enough to read and grep.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import shutil
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import cached_property
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote
from typing import Any, Iterator, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

LOG_FORMAT_VERSION = 1

type Projection = dict[str, Any]
type Event = dict[str, Any]

# Row fields recorded through ``meta.set``. Concurrency bookkeeping
# (state_revision, finalized_revision, state_stage, state_updated_at) and
# background markers (last_result_at) are deliberately left out: they describe
# the running process, not the conversation.
META_FIELDS = (
    "title",
    "pinned",
    "project_id",
    "working_directory",
    "created_at",
    "updated_at",
    "last_active_at",
    "turn_count",
    "context_usage",
)

# Projection keys that come from events rather than from the row.
LOG_ONLY_FIELDS = ("checkpoint",)

MEDIA_THRESHOLD = 64 * 1024
MEDIA_KEY = "$media"
TRASH_RETENTION_DAYS = 30

# Leaves room for ".jsonl" and the ".trash" timestamp within a 255-byte name.
_MAX_FILE_STEM = 200


class ChatLogError(Exception):
    """A chat log cannot be read or folded."""


def normalize_json(value: Any) -> Any:
    """Return *value* exactly as it reads back from the log."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _timestamp(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _is_streaming_draft(message: Any) -> bool:
    return isinstance(message, dict) and bool(message.get("_streaming_draft"))


def project_state(raw: Optional[bytes]) -> dict[str, Any]:
    """Split serialized agent state into its history list and everything else.

    ``None`` (never serialized) and ``b""`` (deliberately cleared) are kept apart
    because callers treat them differently. Anything that is not the JSON
    format written by ``serialize_state`` is stored opaquely as base64.
    """
    if raw is None:
        return {"kind": "none", "meta": {}, "raw": None, "history": []}
    if raw == b"":
        return {"kind": "empty", "meta": {}, "raw": None, "history": []}
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        decoded = None
    if isinstance(decoded, dict) and isinstance(decoded.get("message_history"), list):
        history = decoded.pop("message_history")
        return {
            "kind": "json",
            "meta": decoded,
            "raw": None,
            "history": history,
        }
    return {
        "kind": "raw",
        "meta": {},
        "raw": base64.b64encode(raw).decode("ascii"),
        "history": [],
    }


def state_bytes(state: dict[str, Any]) -> Optional[bytes]:
    """Rebuild agent state bytes from a projected state."""
    match state["kind"]:
        case "none":
            return None
        case "empty":
            return b""
        case "raw":
            return base64.b64decode(state["raw"])
        case _:
            payload = {**state["meta"], "message_history": state["history"]}
            return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")


def visible_messages(messages: Optional[list[Any]]) -> list[Any]:
    """Display messages without the streaming draft, which the log leaves out."""
    return [m for m in (messages or []) if not _is_streaming_draft(m)]


def project_chat(chat: Any) -> Projection:
    """Project a ``chats`` row (ORM object or Core row) onto the logged fields.

    Streaming drafts are dropped: they are overwritten every fraction of a
    second and replaced by the turn's real write, so recording them would fill
    the log with throwaway rows.

    *chat* must be freshly loaded from the database. Its JSON columns are then
    already in the form they read back from the log, which saves re-encoding
    the whole conversation on every write.
    """
    meta = {
        "title": chat.title,
        "pinned": bool(chat.pinned),
        "project_id": chat.project_id,
        "working_directory": chat.working_directory,
        "created_at": _timestamp(chat.created_at),
        "updated_at": _timestamp(chat.updated_at),
        "last_active_at": _timestamp(chat.last_active_at),
        "turn_count": chat.turn_count or 0,
        "context_usage": chat.context_usage or {},
    }
    return {
        **normalize_json(meta),
        "config": chat.config or {},
        "messages": visible_messages(chat.messages),
        "state": project_state(chat.agent_state),
    }


def splice_diff(old: list[Any], new: list[Any]) -> Optional[dict[str, Any]]:
    """Return the single splice turning *old* into *new*, or None if equal.

    The common prefix and suffix are kept, so an appended turn becomes a splice
    at the end and a compaction or rollback becomes one replacement in place.
    """
    prefix = 0
    limit = min(len(old), len(new))
    while prefix < limit and old[prefix] == new[prefix]:
        prefix += 1
    if prefix == len(old) == len(new):
        return None
    suffix = 0
    while (
        suffix < limit - prefix
        and old[len(old) - 1 - suffix] == new[len(new) - 1 - suffix]
    ):
        suffix += 1
    return {
        "start": prefix,
        "delete": len(old) - prefix - suffix,
        "insert": new[prefix : len(new) - suffix],
    }


def apply_splice(items: list[Any], splice: dict[str, Any]) -> list[Any]:
    start, delete = splice["start"], splice["delete"]
    if start < 0 or delete < 0 or start + delete > len(items):
        raise ChatLogError(f"splice {start}+{delete} is outside a list of {len(items)}")
    return items[:start] + list(splice["insert"]) + items[start + delete :]


def _list_changes(
    old: list[Any], new: list[Any], append_kind: str, splice_kind: str
) -> list[tuple[str, Any]]:
    """One event per item appended at the end, otherwise a single splice.

    Nearly every write only appends, so most of a log reads as one message
    per line; rewrites (retry, compaction, rollback) stay one splice.
    """
    splice = splice_diff(old, new)
    if splice is None:
        return []
    if splice["delete"] == 0 and splice["start"] == len(old):
        return [(append_kind, item) for item in splice["insert"]]
    return [(splice_kind, splice)]


def diff_projections(old: Projection, new: Projection) -> list[tuple[str, Any]]:
    """Return the events that turn the row part of *old* into *new*."""
    events: list[tuple[str, Any]] = []

    meta = {key: new[key] for key in META_FIELDS if old.get(key) != new[key]}
    if meta:
        events.append(("meta.set", meta))

    old_config, new_config = old["config"], new["config"]
    changed = {
        key: value
        for key, value in new_config.items()
        if key not in old_config or old_config[key] != value
    }
    removed = [key for key in old_config if key not in new_config]
    if changed or removed:
        events.append(("config.merge", {"set": changed, "unset": removed}))

    events += _list_changes(
        old["messages"], new["messages"], "message.append", "messages.splice"
    )

    old_state, new_state = old["state"], new["state"]
    state_fields = {
        key: new_state[key]
        for key in ("kind", "meta", "raw")
        if old_state[key] != new_state[key]
    }
    if state_fields:
        events.append(("state.set", state_fields))
    events += _list_changes(
        old_state["history"], new_state["history"], "history.append", "history.splice"
    )

    return events


def apply_event(projection: Optional[Projection], event: Event) -> Optional[Projection]:
    """Fold one event into a projection. Returns None once the chat is deleted."""
    if event.get("v") != LOG_FORMAT_VERSION:
        raise ChatLogError(f"unsupported chat log version {event.get('v')!r}")
    kind, data = event["type"], event["data"]

    if kind in ("chat.created", "chat.imported"):
        created = copy.deepcopy(data)
        created.setdefault("checkpoint", None)
        return created
    if kind == "chat.deleted":
        return None
    if projection is None:
        raise ChatLogError(f"{kind} event before the chat was created")

    match kind:
        case "meta.set":
            projection.update(copy.deepcopy(data))
        case "config.merge":
            config = projection["config"]
            config.update(copy.deepcopy(data["set"]))
            for key in data["unset"]:
                config.pop(key, None)
        case "message.append":
            projection["messages"].append(copy.deepcopy(data))
        case "messages.splice":
            projection["messages"] = apply_splice(projection["messages"], data)
        case "state.set":
            projection["state"].update(copy.deepcopy(data))
        case "history.append":
            projection["state"]["history"].append(copy.deepcopy(data))
        case "history.splice":
            state = projection["state"]
            state["history"] = apply_splice(state["history"], data)
        case "checkpoint.set":
            projection["checkpoint"] = copy.deepcopy(data)
        case "checkpoint.update":
            checkpoint = projection.get("checkpoint")
            # An update names the checkpoint it belongs to, so one that lost a
            # race with the next turn's checkpoint changes nothing.
            if checkpoint is not None and checkpoint["id"] == data["id"]:
                checkpoint.update(copy.deepcopy(data["set"]))
        case _:
            raise ChatLogError(f"unknown chat log event type {kind!r}")
    return projection


def projection_differences(
    logged: Optional[Projection], stored: Optional[Projection]
) -> list[str]:
    """Name the row fields where a folded log disagrees with the row."""
    if logged is None or stored is None:
        if logged is stored:
            return []
        return ["<missing log>" if logged is None else "<missing row>"]
    fields = sorted((set(logged) | set(stored)) - set(LOG_ONLY_FIELDS))
    return [field for field in fields if logged.get(field) != stored.get(field)]


@dataclass
class PendingAppend:
    """Events appended to a chat's log whose SQLite commit has not happened yet."""

    chat_id: str
    size_before: int
    projection: Optional[Projection]
    seq: int
    size: int
    mtime_ns: int


@dataclass
class RetryCheckpoint:
    """A chat's retry checkpoint, as its log records it.

    ``before`` is either ``{"seq": n}``, the log position whose state a retry
    restores, or a copy of that state for checkpoints that did not match the
    stored chat. The restored state is read only when a retry needs it.
    """

    chat_id: str
    id: str
    user_message: str
    user_files: list[Any]
    config_snapshot: dict[str, Any]
    has_file_snapshot: bool
    file_snapshot: list[Any]
    created_at: Optional[datetime]
    before: dict[str, Any]
    chat_log: ChatEventLog = field(repr=False, compare=False)

    @classmethod
    def from_logged(
        cls, chat_id: str, data: dict[str, Any], chat_log: ChatEventLog
    ) -> RetryCheckpoint:
        created_at = data.get("created_at")
        return cls(
            chat_id=chat_id,
            id=data["id"],
            user_message=data["user_message"],
            user_files=data["user_files"],
            config_snapshot=data["config_snapshot"],
            has_file_snapshot=data["has_file_snapshot"],
            file_snapshot=data["file_snapshot"],
            created_at=datetime.fromisoformat(created_at) if created_at else None,
            before=data["before"],
            chat_log=chat_log,
        )

    @cached_property
    def _restore_point(self) -> tuple[list[Any], Optional[bytes]]:
        if "seq" in self.before:
            projection, _ = self.chat_log.fold(
                self.chat_id, until_seq=self.before["seq"]
            )
            if projection is None:
                raise ChatLogError(
                    f"{self.chat_id} has no state at seq {self.before['seq']}"
                )
            return projection["messages"], state_bytes(projection["state"])
        return self.before["messages"], state_bytes(self.before["state"])

    @property
    def messages_before(self) -> list[Any]:
        return self._restore_point[0]

    @property
    def agent_state_before(self) -> Optional[bytes]:
        return self._restore_point[1]


class ChatEventLog:
    """Reads, folds and appends the per-chat JSONL logs under one directory."""

    CACHE_SIZE = 64

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.media_root = self.root / ".media"
        self._cache: OrderedDict[str, tuple[Optional[Projection], int]] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._chat_locks: dict[str, threading.Lock] = {}

    def path(self, chat_id: str) -> Path:
        """Map a chat id to its log file.

        Ids are percent-encoded, so peer chats (``suzent:<peer>``) and channel
        ids with any character get a file name that is valid everywhere,
        contains no path separator, and decodes back to the id.
        """
        stem = quote(chat_id, safe="")
        if not stem or len(stem) > _MAX_FILE_STEM:
            raise ChatLogError(f"chat id {chat_id!r} cannot be used as a file name")
        return self.root / f"{stem}.jsonl"

    def chat_ids(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(
            unquote(path.stem) for path in self.root.glob("*.jsonl") if path.is_file()
        )

    def stat(self, chat_id: str) -> Optional[tuple[int, int]]:
        """Return the log's (size, mtime_ns), or None if it has no log."""
        try:
            result = self.path(chat_id).stat()
        except FileNotFoundError:
            return None
        return result.st_size, result.st_mtime_ns

    def lock(self, chat_id: str) -> threading.Lock:
        """The lock to hold from reading a chat's row until its write commits."""
        with self._cache_lock:
            return self._chat_locks.setdefault(chat_id, threading.Lock())

    # Media -----------------------------------------------------------------

    def _store_media(self, text: str) -> str:
        data = text.encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        target = self.media_root / digest
        if not target.exists():
            self.media_root.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(f"{digest}.{os.getpid()}.tmp")
            with partial.open("wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(partial, target)
        return digest

    def _externalize(self, value: Any) -> Any:
        if isinstance(value, str):
            if len(value) >= MEDIA_THRESHOLD:
                return {MEDIA_KEY: self._store_media(value)}
            return value
        if isinstance(value, list):
            return [self._externalize(item) for item in value]
        if isinstance(value, dict):
            return {key: self._externalize(item) for key, item in value.items()}
        return value

    def _resolve(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._resolve(item) for item in value]
        if isinstance(value, dict):
            if len(value) == 1 and isinstance(value.get(MEDIA_KEY), str):
                try:
                    return (self.media_root / value[MEDIA_KEY]).read_text("utf-8")
                except OSError as exc:
                    raise ChatLogError(
                        f"media {value[MEDIA_KEY]} is missing: {exc}"
                    ) from exc
            return {key: self._resolve(item) for key, item in value.items()}
        return value

    # Reading ---------------------------------------------------------------

    def events(self, chat_id: str) -> Iterator[Event]:
        """Yield the log's events, ignoring a torn final line from a crash."""
        path = self.path(chat_id)
        if not path.exists():
            return
        lines = path.read_bytes().split(b"\n")
        # Everything after the last newline is an unfinished write.
        for number, line in enumerate(lines[:-1], start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ChatLogError(f"{path}:{number}: {exc}") from exc
            if not (
                isinstance(event, dict)
                and isinstance(event.get("seq"), int)
                and isinstance(event.get("type"), str)
                and "data" in event
            ):
                raise ChatLogError(f"{path}:{number}: not a chat log event")
            event["data"] = self._resolve(event["data"])
            yield event

    def fold(
        self, chat_id: str, until_seq: Optional[int] = None
    ) -> tuple[Optional[Projection], int]:
        """Replay a chat's log, optionally stopping after event *until_seq*.

        Returns the projection and the last sequence number applied.
        """
        projection: Optional[Projection] = None
        seq = 0
        for event in self.events(chat_id):
            if until_seq is not None and event["seq"] > until_seq:
                break
            try:
                projection = apply_event(projection, event)
            except (KeyError, TypeError, AttributeError) as exc:
                raise ChatLogError(
                    f"{chat_id} event {event['seq']} is malformed: {exc!r}"
                ) from exc
            seq = event["seq"]
        return projection, seq

    def logged(self, chat_id: str) -> tuple[Optional[Projection], int]:
        """The chat's current projection and sequence number, from the cache.

        Hold :meth:`lock` while using the result: the cached projection is
        shared and is replaced by the next write.
        """
        with self._cache_lock:
            if chat_id in self._cache:
                self._cache.move_to_end(chat_id)
                return self._cache[chat_id]
        path = self.path(chat_id)
        self._drop_torn_tail(path)
        try:
            projection, seq = self.fold(chat_id)
        except ChatLogError as exc:
            # The row is now the best remaining copy; the next write starts a
            # fresh log from it and the unreadable one is kept for inspection.
            kept = self._move_aside(path, ".corrupt")
            logger.warning("Chat log {} is unreadable, kept as {}: {}", path, kept, exc)
            projection, seq = None, 0
        self._remember(chat_id, projection, seq)
        return projection, seq

    def _remember(
        self, chat_id: str, projection: Optional[Projection], seq: int
    ) -> None:
        with self._cache_lock:
            self._cache[chat_id] = (projection, seq)
            self._cache.move_to_end(chat_id)
            while len(self._cache) > self.CACHE_SIZE:
                self._cache.popitem(last=False)

    def forget(self, chat_id: str) -> None:
        with self._cache_lock:
            self._cache.pop(chat_id, None)

    # Writing ---------------------------------------------------------------

    def _drop_torn_tail(self, path: Path) -> None:
        if not path.exists():
            return
        with path.open("rb+") as handle:
            data = handle.read()
            if data and not data.endswith(b"\n"):
                handle.truncate(data.rfind(b"\n") + 1)

    def _append(self, path: Path, events: list[Event]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = "".join(
            json.dumps(
                {**event, "data": self._externalize(event["data"])},
                ensure_ascii=False,
                default=str,
            )
            + "\n"
            for event in events
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

    def prepare(
        self,
        chat_id: str,
        current: Optional[Projection],
        *,
        created: bool = False,
        extra: tuple[tuple[str, Any], ...] = (),
    ) -> Optional[PendingAppend]:
        """Append and fsync the events that bring the log up to *current*.

        *current* is the projection of the chat's uncommitted row, or None if
        the write deletes it. *extra* holds log-only events (``checkpoint.*``)
        appended after the row's changes; a ``checkpoint.set`` whose ``before``
        is ``{"seq": None}`` is pinned to the event just ahead of it.

        The caller holds :meth:`lock` and then either commits SQLite and calls
        :meth:`confirm`, or calls :meth:`undo`. Returns None if nothing changed.
        """
        path = self.path(chat_id)
        logged, seq = self.logged(chat_id)
        if current is None:
            if logged is None:
                return None
            pending: list[tuple[str, Any]] = [("chat.deleted", {})]
        else:
            if logged is None:
                # The opening event carries everything but the two lists, whose
                # items follow one per line like any later append.
                kind = "chat.created" if created else "chat.imported"
                empty = {
                    **current,
                    "messages": [],
                    "state": {**current["state"], "history": []},
                }
                pending = [(kind, empty), *diff_projections(empty, current)]
            else:
                pending = diff_projections(logged, current)
            current["checkpoint"] = (
                copy.deepcopy(logged.get("checkpoint")) if logged else None
            )
            pending += list(extra)
        if not pending:
            return None

        events = []
        for offset, (kind, data) in enumerate(pending, start=1):
            if kind == "checkpoint.set" and data.get("before") == {"seq": None}:
                data = {**data, "before": {"seq": seq + offset - 1}}
            events.append(self._event(seq + offset, kind, data))
        if current is not None:
            for event in events[len(events) - len(extra) :]:
                apply_event(current, event)

        size_before = path.stat().st_size if path.exists() else 0
        try:
            self._append(path, events)
        except BaseException:
            self._truncate(path, size_before)
            raise
        stat = path.stat()
        return PendingAppend(
            chat_id=chat_id,
            size_before=size_before,
            projection=current,
            seq=events[-1]["seq"],
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
        )

    def confirm(self, pending: PendingAppend) -> None:
        """SQLite committed: cache the new projection, retire a deleted log."""
        if pending.projection is None:
            self.retire(pending.chat_id)
            return
        self._remember(pending.chat_id, pending.projection, pending.seq)

    def undo(self, pending: PendingAppend) -> None:
        """SQLite did not commit: take the appended events back out."""
        self._truncate(self.path(pending.chat_id), pending.size_before)
        self.forget(pending.chat_id)

    def _truncate(self, path: Path, size: int) -> None:
        if not path.exists():
            return
        if size == 0:
            path.unlink()
        else:
            os.truncate(path, size)

    def retire(self, chat_id: str) -> None:
        """Move a deleted chat's log to ``.trash/``."""
        path = self.path(chat_id)
        if path.exists():
            self._move_aside(path, ".trash")
        self._remember(chat_id, None, 0)

    def _move_aside(self, path: Path, folder: str) -> Path:
        target_dir = self.root / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = target_dir / f"{path.stem}.{stamp}.jsonl"
        shutil.move(str(path), target)
        # Retention counts from when the log was set aside, not its last write.
        os.utime(target)
        return target

    def purge_trash(self, max_age_days: int = TRASH_RETENTION_DAYS) -> int:
        """Delete trashed logs older than *max_age_days*. Returns how many."""
        trash = self.root / ".trash"
        if not trash.is_dir():
            return 0
        cutoff = time.time() - max_age_days * 86400
        purged = 0
        for path in trash.glob("*.jsonl"):
            if path.stat().st_mtime < cutoff:
                path.unlink()
                purged += 1
        return purged

    @staticmethod
    def _event(seq: int, kind: str, data: Any) -> Event:
        return {
            "v": LOG_FORMAT_VERSION,
            "seq": seq,
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": kind,
            "data": data,
        }


def default_log_root(db_path: Path) -> Path:
    """``<data>/chats.db`` keeps its logs in ``<data>/chats/``."""
    return db_path.parent / db_path.stem
