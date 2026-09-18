"""Runtime-independent snapshots and cursors for browser stream recovery.

All mutations and snapshot reads run on the event loop, so a snapshot and its
cursor describe the same instant. Snapshots compact adjacent deltas without
interpreting runtime-specific custom events; clients use their existing reducer.
"""

import asyncio
from collections import deque
from collections.abc import AsyncGenerator
import json
import time
from typing import Any
from uuid import uuid4


_DELTA_TYPES = {
    "TEXT_MESSAGE_CONTENT",
    "THINKING_TEXT_MESSAGE_CONTENT",
    "REASONING_MESSAGE_CONTENT",
    "REASONING_MESSAGE_CHUNK",
    "TOOL_CALL_ARGS",
}


class StreamReplay:
    def __init__(self, capacity: int = 4096) -> None:
        self.run_id = uuid4().hex
        self.seq = 0
        self.closed = False
        self.superseded = False
        self.closed_at: float | None = None
        # Resolves True once this turn is in the database. A task on the native
        # path (post-processing runs after the stream closes), a plain future on
        # the ACP path (the write is synchronous, so it is resolved inline).
        # None means no producer claimed the contract — treated as persisted,
        # which is why every recoverable producer must attach one.
        self.persistence: asyncio.Future[bool] | None = None
        # The name the client gave this turn when it asked for it, minted before
        # the POST. `run_id` only reaches the client once the first protocol
        # frame does, so between "Stop is clickable" and that frame this is the
        # only name a stop can use for the run it means. None for turns nobody
        # named (schedulers, sub-agents, inbox deliveries).
        self.client_token: str | None = None
        # A stop accepted for this run before the run had a control to take it.
        # /chat/steer-send installs the replacement replay (and its name) while
        # the turn being replaced is still the one holding the chat's control,
        # so a stop landing in that window must travel with the run it named
        # and be taken when that run finally starts.
        self.stop_requested: str | None = None
        # Whether this run's producer is running, and so can take a stop
        # itself. False covers both "the turn has not started yet" and the
        # window a steer opens by registering this replay before the turn it
        # replaces has been cancelled -- where a cancellation aimed at the chat
        # would land on that other turn.
        self.producer_started: bool = False
        self.events: list[dict[str, Any]] = []
        self.tail: deque[tuple[int, dict[str, Any]]] = deque(maxlen=capacity)
        self.changed = asyncio.Event()
        self._buffer = ""
        self._delta_fragments: list[str] = []

    def append(self, chunk: str | None) -> None:
        if self.closed:
            return
        if chunk is None:
            self.closed = True
            self.closed_at = time.monotonic()
        else:
            self._buffer += chunk.replace("\r\n", "\n")
            blocks = self._buffer.split("\n\n")
            self._buffer = blocks.pop()
            for block in blocks:
                data = "\n".join(
                    line[5:].lstrip()
                    for line in block.splitlines()
                    if line.startswith("data:")
                )
                if not data:
                    continue
                try:
                    event = json.loads(data)
                except ValueError:
                    continue
                if not isinstance(event, dict) or not isinstance(
                    event.get("type"), str
                ):
                    continue
                self.seq += 1
                self.tail.append((self.seq, event))
                previous = self.events[-1] if self.events else None
                if (
                    previous is not None
                    and event["type"] in _DELTA_TYPES
                    and isinstance(event.get("delta"), str)
                    and isinstance(previous.get("delta"), str)
                    and {
                        k: v
                        for k, v in event.items()
                        if k not in {"delta", "timestamp"}
                    }
                    == {
                        k: v
                        for k, v in previous.items()
                        if k not in {"delta", "timestamp"}
                    }
                ):
                    self._delta_fragments.append(event["delta"])
                else:
                    self._flush_deltas()
                    self.events.append(event)
                    if event["type"] in _DELTA_TYPES and isinstance(
                        event.get("delta"), str
                    ):
                        self._delta_fragments = [event["delta"]]
        changed = self.changed
        self.changed = asyncio.Event()
        changed.set()

    def _flush_deltas(self) -> None:
        if self._delta_fragments:
            self.events[-1] = {
                **self.events[-1],
                "delta": "".join(self._delta_fragments),
            }
            self._delta_fragments = []

    def _snapshot_events(self) -> list[dict[str, Any]]:
        events = list(self.events)
        if self._delta_fragments:
            events[-1] = {**events[-1], "delta": "".join(self._delta_fragments)}
        return events

    def read(self, run_id: str | None, after_seq: int | None) -> list[dict[str, Any]]:
        oldest = self.tail[0][0] if self.tail else self.seq + 1
        if (
            run_id != self.run_id
            or after_seq is None
            or after_seq < oldest - 1
            or after_seq > self.seq
        ):
            return [
                {
                    "type": "STREAM_SNAPSHOT",
                    "run_id": self.run_id,
                    "seq": self.seq,
                    "events": self._snapshot_events(),
                }
            ]
        return [
            {"type": "STREAM_EVENT", "run_id": self.run_id, "seq": seq, "event": event}
            for seq, event in self.tail
            if seq > after_seq
        ]

    @property
    def persisted(self) -> bool:
        return self.closed and (
            self.persistence is None
            or (
                self.persistence.done()
                and not self.persistence.cancelled()
                and self.persistence.exception() is None
                and self.persistence.result() is True
            )
        )

    async def subscribe(
        self,
        run_id: str | None = None,
        after_seq: int | None = None,
    ) -> AsyncGenerator[str, None]:
        while True:
            changed = self.changed
            updates = self.read(run_id, after_seq)
            for update in updates:
                run_id, after_seq = update["run_id"], update["seq"]
                if update["type"] == "STREAM_SNAPSHOT":
                    payload = await asyncio.to_thread(
                        json.dumps, update, ensure_ascii=False
                    )
                else:
                    payload = json.dumps(update, ensure_ascii=False)
                yield f"data: {payload}\n\n"
            if self.closed and after_seq == self.seq:
                while (
                    not self.superseded
                    and self.persistence is not None
                    and not self.persistence.done()
                ):
                    done, _ = await asyncio.wait({self.persistence}, timeout=20)
                    if not done:
                        yield ": keep-alive\n\n"
                yield f"data: {json.dumps({'type': 'STREAM_END', 'run_id': self.run_id, 'seq': self.seq, 'persisted': self.persisted, 'superseded': self.superseded})}\n\n"
                return
            try:
                await asyncio.wait_for(changed.wait(), timeout=20)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
