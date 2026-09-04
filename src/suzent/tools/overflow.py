"""Somewhere to put the part of an output that did not fit.

A cap keeps a single tool result from swallowing the context window, but the
tail it removes is usually the part someone wanted: the failing assertion at the
end of a test run, the last hundred lines of a build log. Truncating to a marker
tells the model that content is missing without giving it any way to read it.

So the full text is written to a file and the marker carries the path.

Two properties are load-bearing and easy to lose:

* **The write must not become a capability.** The agent can write inside
  ``/shared`` — including replacing the directories on this path — so every step
  is taken relative to a pinned directory descriptor and refuses to follow a
  symlink. Resolving a path and then using it is a race the agent can win.
* **A spill is private to its chat.** It holds raw tool output and reminder
  text, which is conversation content. ``/shared`` is mounted into every
  session, so an unscoped directory is readable by every other chat on the
  deployment; random filenames are no help against a directory listing.
"""

from __future__ import annotations

import asyncio
import errno
import os
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

#: Virtual home for spilled output, under /shared so a spill survives the
#: container and so the sweep can find every chat's files in one place.
OVERFLOW_VIRTUAL_DIR = "/shared/.overflow"

#: How long a spill is worth keeping. Long enough to read it later in the same
#: session, short enough that a week of build logs does not accumulate.
OVERFLOW_TTL_SECONDS = 24 * 60 * 60

#: Per-chat ceilings. A single runaway session can write thousands of files, and
#: 200 files of any size is not a bound on disk, so both apply.
OVERFLOW_MAX_FILES = 200
OVERFLOW_MAX_TOTAL_BYTES = 50 * 1024 * 1024

#: Ceiling on one spill. A foreground shell command reads its whole output into
#: memory and this writes all of it.
OVERFLOW_MAX_FILE_BYTES = 5 * 1024 * 1024

#: Written into a spill that had to be cut. The marker says so as well; this is
#: for whoever opens the file directly.
SPILL_CLIPPED_NOTE = "\n\n[spill clipped: output exceeded the per-file limit]"

_SAFE_SEGMENT = re.compile(r"[^A-Za-z0-9_-]")

#: dir_fd is POSIX-only. Where it is missing there is also no bind-mounted
#: sandbox writing into this directory, so plain path operations are used.
_HAVE_DIR_FD = os.open in os.supports_dir_fd and os.unlink in os.supports_dir_fd


@dataclass(frozen=True)
class Spill:
    """Where the overflow went, and whether all of it got there."""

    path: str
    clipped: bool


def retention_hint() -> str:
    """How long a spill may last, for the marker that points at one.

    The marker outlives the file: the path goes into conversation history, the
    file expires. Saying the window turns a puzzling missing file into an
    expected one.

    "up to", because the count and byte ceilings evict early — eleven
    maximum-sized results inside an hour will drop the first of them long before
    the day is out. Promising a duration the storage bounds can overrule is the
    same defect as promising a full output that was clipped.

    Derived from the TTL so the two cannot drift.
    """
    return f"kept up to {OVERFLOW_TTL_SECONDS // 3600}h"


def _chat_segment(deps: Any) -> str:
    """A directory name for this chat, safe to place in a path."""
    raw = str(getattr(deps, "chat_id", "") or "shared")
    return _SAFE_SEGMENT.sub("-", raw)[:64] or "shared"


def _open_child_dir(name: str, *, parent_fd: Optional[int], base: Path) -> int:
    """Open (creating if needed) a subdirectory, refusing to follow a symlink.

    Taken relative to *parent_fd* so a directory swapped for a symlink after the
    parent was opened cannot redirect the write. Without dir_fd support the same
    steps run against a path.
    """
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    if parent_fd is None:
        target = base / name
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        return os.open(target, flags)

    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    return os.open(name, flags, dir_fd=parent_fd)


def _clip(text: str) -> tuple[bytes, bool]:
    """Encode *text*, cut to the per-file ceiling on a character boundary.

    Slicing the encoded bytes can land inside a multi-byte code point, and the
    resulting file is not valid UTF-8 — so the reader that was supposed to
    rescue the output fails to open it.
    """
    payload = text.encode("utf-8", "replace")
    if len(payload) <= OVERFLOW_MAX_FILE_BYTES:
        return payload, False

    note = SPILL_CLIPPED_NOTE.encode("utf-8")
    keep = OVERFLOW_MAX_FILE_BYTES - len(note)
    head = payload[:keep].decode("utf-8", "ignore").encode("utf-8")
    return head + note, True


def _prune_fd(dir_fd: int) -> None:
    """Apply the retention bounds inside one pinned directory."""
    try:
        entries = []
        for entry in os.scandir(dir_fd):
            if not entry.name.endswith(".txt"):
                continue
            try:
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            entries.append((stat.st_mtime, stat.st_size, entry.name))
    except OSError:
        return

    entries.sort(reverse=True)
    cutoff = time.time() - OVERFLOW_TTL_SECONDS
    running = 0
    for index, (mtime, size, name) in enumerate(entries):
        drop = (
            index >= OVERFLOW_MAX_FILES
            or mtime < cutoff
            or running + size > OVERFLOW_MAX_TOTAL_BYTES
        )
        try:
            if drop:
                os.unlink(name, dir_fd=dir_fd)
            else:
                running += size
        except OSError:
            continue


def spill_overflow(text: str, *, deps: Any, kind: str = "output") -> Optional[Spill]:
    """Write *text* somewhere this chat can read it; return where it went.

    Returns None when there is nowhere to write, which is not an error: the
    caller still truncates, it just cannot offer the rest. Losing the tail is
    better than failing the tool call that produced it.

    The path handed back is in the vocabulary of the agent's own filesystem —
    host paths in host mode, virtual in sandbox — because a path it cannot open
    invites a read that fails.
    """
    resolver = getattr(deps, "path_resolver", None)
    if resolver is None:
        return None

    # Sandbox mode gets the plain marker instead of a file.
    #
    # Every container bind-mounts the same host `shared` directory read-write
    # and every one of them runs as uid 1000, so a per-chat subdirectory is a
    # naming convention and not a boundary: chat B lists and reads chat A's
    # spills whatever the mode bits say. Spills hold raw tool output and
    # reminder text, which is conversation content, so the honest options are a
    # per-chat mount or not writing the file — and a convenience feature does
    # not get to widen the isolation model on its way in.
    #
    # Host mode has no such boundary to breach: the agent already reaches the
    # whole filesystem through its shell, so the spill exposes nothing that was
    # not reachable already.
    if getattr(deps, "sandbox_enabled", True):
        return None

    try:
        shared_host = Path(resolver.resolve("/shared"))
    except Exception as e:
        logger.debug(f"[overflow] no shared root: {e}")
        return None

    chat = _chat_segment(deps)
    root_fd = None
    overflow_fd = None
    chat_fd = None
    try:
        if _HAVE_DIR_FD:
            shared_host.mkdir(parents=True, exist_ok=True)
            root_fd = os.open(shared_host, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            overflow_fd = _open_child_dir(
                ".overflow", parent_fd=root_fd, base=shared_host
            )
            chat_fd = _open_child_dir(chat, parent_fd=overflow_fd, base=shared_host)
        else:
            chat_fd = _open_child_dir(
                chat, parent_fd=None, base=shared_host / ".overflow"
            )

        payload, clipped = _clip(text)
        name = f"{kind}-{secrets.token_hex(16)}.txt"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)

        try:
            fd = os.open(name, flags, 0o600, dir_fd=chat_fd)
        except OSError as e:
            if e.errno in (errno.EEXIST, errno.ELOOP):
                logger.warning(f"[overflow] refusing to write over {name}: {e}")
            else:
                logger.debug(f"[overflow] could not create spill: {e}")
            return None

        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
        except OSError as e:
            logger.debug(f"[overflow] could not write spill: {e}")
            try:
                os.unlink(name, dir_fd=chat_fd)
            except OSError:
                pass
            return None

        _prune_fd(chat_fd)
    except OSError as e:
        logger.debug(f"[overflow] no spill directory: {e}")
        return None
    finally:
        for handle_fd in (chat_fd, overflow_fd, root_fd):
            if handle_fd is not None:
                try:
                    os.close(handle_fd)
                except OSError:
                    pass

    if getattr(deps, "sandbox_enabled", True):
        return Spill(f"{OVERFLOW_VIRTUAL_DIR}/{chat}/{name}", clipped)
    return Spill(str(shared_host / ".overflow" / chat / name), clipped)


async def spill_overflow_async(
    text: str, *, deps: Any, kind: str = "output"
) -> Optional[Spill]:
    """Spill without holding the event loop.

    Up to 5 MiB of write plus a directory scan; on a slow volume, or with
    several overflows at once, doing that inline stalls every other chat the
    loop is serving.
    """
    return await asyncio.to_thread(spill_overflow, text, deps=deps, kind=kind)


def sweep_overflow() -> None:
    """Apply the retention bounds without needing a spill to trigger them.

    Pruning otherwise happens only on write, so the bounds hold exactly while
    output keeps overflowing and stop the moment it does not: the last spill of
    a session sits there until the next one, which may be never. Nothing else
    collects these — they live in the user's data directory, not a temp
    directory the OS sweeps.

    Per-chat bounds mean the directory total scales with the number of chats,
    which is why this also drops chat directories once they are empty.
    """
    from suzent.config import CONFIG

    root = Path(CONFIG.sandbox_data_path) / "shared" / ".overflow"
    if not root.is_dir():
        return

    # Descended with the same no-follow discipline as the write path. A symlink
    # left as a child of .overflow would otherwise be followed twice — once by
    # is_dir(), once by the open — and _prune_fd unlinks, so the sweep would
    # delete *.txt files in a directory of the sandbox's choosing on the next
    # restart. The write path was pinned and this was not; the attacker picks
    # the weaker one.
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        root_fd = os.open(root, flags)
    except OSError as e:
        logger.debug(f"[overflow] cannot open the spill root: {e}")
        return

    swept = 0
    try:
        for entry in os.scandir(root_fd):
            if not entry.is_dir(follow_symlinks=False):
                continue
            try:
                chat_fd = os.open(entry.name, flags, dir_fd=root_fd)
            except OSError:
                continue
            try:
                before = sum(1 for _ in os.scandir(chat_fd))
                _prune_fd(chat_fd)
                after = sum(1 for _ in os.scandir(chat_fd))
                swept += before - after
            finally:
                os.close(chat_fd)
            if after == 0:
                try:
                    os.rmdir(entry.name, dir_fd=root_fd)
                except OSError:
                    pass
    except OSError:
        pass
    finally:
        os.close(root_fd)

    if swept:
        logger.info(f"[overflow] swept {swept} stale spill(s)")
