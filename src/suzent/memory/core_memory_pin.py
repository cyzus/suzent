"""Keep the core-memory section of the system prompt fixed for a chat.

Core memory sits in the system prompt, ahead of the whole conversation, and the
system prompt is rebuilt on every model request. Any edit — the agent updating
the project's context.md mid-run, a dream rewriting MEMORY.md, another chat
touching user.md — used to change that prefix, and every provider then
re-reads the entire history behind it at full price.

So each chat pins the version it started with. Later edits reach the model as
a diff in a system reminder on the next turn, which lands after the cached
history instead of in front of it. The pin is replaced only when nothing cached
is lost by replacing it: a chat with no model response yet, a process that has
no pin for the chat, a compaction (which rewrites the history anyway), or an
edit too large to state as a diff.

Pins are keyed by chat *and* user and live in this process, never on the agent:
the agent is cached across chats and users, so a snapshot held there would be
served to the next requester (see ``prompts.inject_memory_context``).
"""

from __future__ import annotations

import difflib
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from suzent.logger import get_logger

logger = get_logger(__name__)

type PinKey = tuple[str, str]

#: Diffs larger than this re-pin the system prompt instead. Past this size the
#: reminder would crowd out other context under REMINDER_BUDGET_CHARS, and an
#: edit that large (a regenerated MEMORY.md) costs about as much to send as the
#: cache miss it would avoid.
MAX_DIFF_CHARS = 2500

#: Chats remembered at once. An evicted chat re-pins on its next request, which
#: costs one cache miss and nothing else.
MAX_PINNED_CHATS = 512

UPDATE_HEADER = (
    "# Core Memory Update\n"
    "Core memory changed since you last saw it. The Core Memory section of the "
    "system prompt is not refreshed mid-conversation; treat it as amended by "
    "this diff and any earlier Core Memory Update."
)


@dataclass
class _Pin:
    #: What the system prompt shows for this chat.
    pinned: str
    #: The latest version the model has been told about, by prompt or reminder.
    seen: str
    #: A version offered in a reminder that has not been confirmed delivered.
    pending: str | None = None


def render_diff(old: str, new: str) -> str:
    lines = difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=1)
    # The ---/+++ file headers name nothing useful here.
    return "\n".join(line for i, line in enumerate(lines) if i >= 2)


class CoreMemoryPins:
    """Per-chat pinned core memory and the diffs owed since the pin."""

    def __init__(self, max_chats: int = MAX_PINNED_CHATS) -> None:
        self._pins: OrderedDict[PinKey, _Pin] = OrderedDict()
        self._max_chats = max_chats
        self._lock = threading.Lock()

    def resolve(self, key: PinKey, live: str, *, fresh: bool) -> str:
        """The core-memory text this chat's system prompt should carry.

        *fresh* means the conversation has no model response yet, so there is
        no cached prefix to protect and the pin can follow *live*.
        """
        with self._lock:
            pin = self._pins.get(key)
            if fresh or pin is None:
                pin = _Pin(pinned=live, seen=live)
                self._pins[key] = pin
            self._pins.move_to_end(key)
            while len(self._pins) > self._max_chats:
                self._pins.popitem(last=False)
            return pin.pinned

    def take_update(self, key: PinKey, live: str) -> str | None:
        """A reminder describing what changed since the model last saw core memory.

        *live* becomes seen only once ``acknowledge`` confirms the reminder
        survived the reminder budget; until then the same change is offered
        again, so a dropped reminder is retried rather than lost. Returns None when
        nothing changed, when the chat has no pin yet (the next request pins
        *live* directly), or when the change is too large for a diff — then the
        pin itself moves to *live* and the system prompt carries it.
        """
        with self._lock:
            pin = self._pins.get(key)
            if pin is None or pin.seen == live:
                return None
            diff = render_diff(pin.seen, live)
            if not diff.strip() or len(diff) > MAX_DIFF_CHARS:
                logger.debug(
                    f"[core-memory-pin] chat={key[0]} re-pinned "
                    f"(diff {len(diff)} chars)"
                )
                pin.pinned = live
                pin.seen = live
                pin.pending = None
                return None
            pin.pending = live
        return f"{UPDATE_HEADER}\n```diff\n{diff}\n```"

    def acknowledge(self, key: PinKey) -> None:
        """The reminder from the last ``take_update`` reached the model."""
        with self._lock:
            pin = self._pins.get(key)
            if pin is not None and pin.pending is not None:
                pin.seen = pin.pending
                pin.pending = None

    def forget(self, chat_id: str) -> None:
        """Drop the chat's pin, for when its history was rewritten anyway."""
        with self._lock:
            for key in [k for k in self._pins if k[0] == chat_id]:
                del self._pins[key]

    def clear(self) -> None:
        with self._lock:
            self._pins.clear()


core_memory_pins = CoreMemoryPins()


def pin_key(deps: Any) -> PinKey | None:
    """The pin a run belongs to, or None when it must not share one.

    Stateless runs (dream, sub-agents) never receive reminders, so a pin would
    hide edits from them for good; they always read core memory live.
    """
    chat_id = getattr(deps, "chat_id", "") or ""
    if not chat_id or getattr(deps, "stateless", False):
        return None
    return (chat_id, getattr(deps, "user_id", "") or "")


async def core_memory_reminder_hook(chat_id: str, deps: Any) -> str | None:
    """Global reminder hook: the core-memory diff owed since the chat's pin."""
    key = pin_key(deps)
    if key is None or getattr(deps, "memory_manager", None) is None:
        return None
    from suzent.prompts import render_core_memory

    live = await render_core_memory(deps)
    if not live:
        # A failed read is not an edit; telling the model its memory was
        # deleted would be worse than saying nothing this turn.
        return None
    return core_memory_pins.take_update(key, live)


def _acknowledge_delivery(chat_id: str, deps: Any) -> None:
    key = pin_key(deps)
    if key is not None:
        core_memory_pins.acknowledge(key)


core_memory_reminder_hook.on_delivered = _acknowledge_delivery  # type: ignore[attr-defined]
