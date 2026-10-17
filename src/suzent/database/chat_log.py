"""Append-only JSONL event log for each chat.

Each chat gets ``<root>/<chat_id>.jsonl``. Every line is one event:

    {"v": 1, "seq": 7, "ts": "...", "type": "messages.splice", "data": {...}}

Folding a chat's events with :func:`apply_event` yields its *projection*: the
durable parts of the ``chats`` row in a JSON-only form (see :func:`project_chat`).
The log only ever records differences between successive projections, so its
size grows with the conversation rather than with the number of writes.

In ``shadow`` mode SQLite stays the source of truth: after a chat write commits,
the database layer projects the stored row and :meth:`ChatEventLog.sync` appends
whatever changed. ``suzent chats verify`` folds each log and compares it with
the row, which is the evidence needed before the log can become authoritative.
"""

from __future__ import annotations

import base64
import copy
import json
import os
import shutil
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote
from typing import Any, Callable, Iterator, Optional

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

# Leaves room for ".jsonl" and the ".trash" timestamp within a 255-byte name.
_MAX_FILE_STEM = 200


class ChatLogError(Exception):
    """A chat log cannot be read or folded."""


def _normalize(value: Any) -> Any:
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


def project_chat(chat: Any) -> Projection:
    """Project a ``ChatModel`` row onto the fields the log records.

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
    messages = [m for m in (chat.messages or []) if not _is_streaming_draft(m)]
    return {
        **_normalize(meta),
        "config": chat.config or {},
        "messages": messages,
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


def diff_projections(old: Projection, new: Projection) -> list[tuple[str, Any]]:
    """Return the events that turn projection *old* into *new*."""
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

    if splice := splice_diff(old["messages"], new["messages"]):
        events.append(("messages.splice", splice))

    old_state, new_state = old["state"], new["state"]
    state_fields = {
        key: new_state[key]
        for key in ("kind", "meta", "raw")
        if old_state[key] != new_state[key]
    }
    if state_fields:
        events.append(("state.set", state_fields))
    if splice := splice_diff(old_state["history"], new_state["history"]):
        events.append(("history.splice", splice))

    return events


def apply_event(projection: Optional[Projection], event: Event) -> Optional[Projection]:
    """Fold one event into a projection. Returns None once the chat is deleted."""
    if event.get("v") != LOG_FORMAT_VERSION:
        raise ChatLogError(f"unsupported chat log version {event.get('v')!r}")
    kind, data = event["type"], event["data"]

    if kind in ("chat.created", "chat.imported"):
        return copy.deepcopy(data)
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
        case "messages.splice":
            projection["messages"] = apply_splice(projection["messages"], data)
        case "state.set":
            projection["state"].update(copy.deepcopy(data))
        case "history.splice":
            state = projection["state"]
            state["history"] = apply_splice(state["history"], data)
        case _:
            raise ChatLogError(f"unknown chat log event type {kind!r}")
    return projection


class ChatEventLog:
    """Reads, folds and appends the per-chat JSONL logs under one directory."""

    CACHE_SIZE = 64

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
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
        return sorted(unquote(path.stem) for path in self.root.glob("*.jsonl"))

    def _lock(self, chat_id: str) -> threading.Lock:
        with self._cache_lock:
            return self._chat_locks.setdefault(chat_id, threading.Lock())

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
            yield event

    def fold(self, chat_id: str) -> tuple[Optional[Projection], int]:
        """Replay a chat's log. Returns its projection and last sequence number."""
        projection: Optional[Projection] = None
        seq = 0
        for event in self.events(chat_id):
            try:
                projection = apply_event(projection, event)
            except (KeyError, TypeError, AttributeError) as exc:
                raise ChatLogError(
                    f"{chat_id} event {event['seq']} is malformed: {exc!r}"
                ) from exc
            seq = event["seq"]
        return projection, seq

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
            json.dumps(event, ensure_ascii=False, default=str) + "\n"
            for event in events
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()

    def _cached(self, chat_id: str) -> tuple[Optional[Projection], int]:
        with self._cache_lock:
            if chat_id in self._cache:
                self._cache.move_to_end(chat_id)
                return self._cache[chat_id]
        self._drop_torn_tail(self.path(chat_id))
        return self.fold(chat_id)

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

    def sync(
        self,
        chat_id: str,
        load: Callable[[], Optional[Projection]],
        *,
        created: bool = False,
    ) -> int:
        """Append the events that bring the log up to the chat's current state.

        *load* reads the committed row and returns its projection, or None once
        the chat no longer exists: the log then records the deletion and moves
        to ``.trash/``. It runs under the chat's lock, so two writers syncing at
        once cannot append an older state after a newer one. Returns the number
        of events written.
        """
        path = self.path(chat_id)
        with self._lock(chat_id):
            try:
                current = load()
                logged, seq = self._cached(chat_id)
                if current is None:
                    if logged is None:
                        return 0
                    self._append(path, [self._event(seq + 1, "chat.deleted", {})])
                    self._move_to_trash(path)
                    self._remember(chat_id, None, 0)
                    return 1
                if logged is None:
                    pending = [
                        ("chat.created" if created else "chat.imported", current)
                    ]
                else:
                    pending = diff_projections(logged, current)
                if not pending:
                    return 0
                events = [
                    self._event(seq + offset, kind, data)
                    for offset, (kind, data) in enumerate(pending, start=1)
                ]
                self._append(path, events)
                # load() built this projection fresh and nothing else holds it.
                self._remember(chat_id, current, events[-1]["seq"])
                return len(events)
            except Exception:
                # A failed append may leave a torn line; refold on the next write.
                self.forget(chat_id)
                raise

    def _move_to_trash(self, path: Path) -> None:
        trash = self.root / ".trash"
        trash.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        shutil.move(str(path), trash / f"{path.stem}.{stamp}.jsonl")

    @staticmethod
    def _event(seq: int, kind: str, data: Any) -> Event:
        return {
            "v": LOG_FORMAT_VERSION,
            "seq": seq,
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": kind,
            "data": data,
        }


def projection_differences(
    logged: Optional[Projection], stored: Optional[Projection]
) -> list[str]:
    """Name the top-level fields where a folded log disagrees with the row."""
    if logged is None or stored is None:
        if logged is stored:
            return []
        return ["<missing log>" if logged is None else "<missing row>"]
    fields = sorted(set(logged) | set(stored))
    return [field for field in fields if logged.get(field) != stored.get(field)]


def default_log_root(db_path: Path) -> Path:
    """``<data>/chats.db`` keeps its logs in ``<data>/chats/``."""
    return db_path.parent / db_path.stem


def shadow_enabled() -> bool:
    """Whether chat writes are mirrored to the JSONL log."""
    if os.getenv("SUZENT_CHAT_STORE"):
        return os.environ["SUZENT_CHAT_STORE"] == "shadow"
    try:
        from suzent.config import CONFIG

        return getattr(CONFIG, "chat_store", "shadow") == "shadow"
    except Exception:
        return True
