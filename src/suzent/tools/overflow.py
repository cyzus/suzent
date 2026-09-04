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
* **A spill is not private to its chat, by decision.** Every sandbox container
  bind-mounts the same host ``shared`` directory and every one runs as uid
  1000, so one chat can read another's spills whatever the mode bits say.
  Suzent has a single owner, who has accepted that: their chats reading each
  other is their own data reaching their own agent.

  This is a property of the deployment, not of the code, so it is worth stating
  what would change it. Inbound channels mean other people's messages become
  chat content; if their conversations ever need to be private *from each
  other*, the boundary has to be a per-chat mount, because permissions on one
  shared mount with one uid cannot express it. Per-chat directories here are
  organisation and pruning scope, not access control, and should not be
  mistaken for it.
"""

from __future__ import annotations

import asyncio
import errno
import os
import re
import secrets
import threading
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

#: Deployment-wide ceiling, enforced by the sweep.
#:
#: Pruning on write only ever sees one chat's directory, so the per-chat
#: allowance multiplies by the number of chats: a hundred of them retain 5 GiB
#: while every directory is individually within bounds. Inbound channels mean
#: chats can be created by someone other than the owner, so that count is not
#: self-limiting.
OVERFLOW_MAX_ROOT_BYTES = 250 * 1024 * 1024

#: Ceiling on one spill. A foreground shell command reads its whole output into
#: memory and this writes all of it.
OVERFLOW_MAX_FILE_BYTES = 5 * 1024 * 1024

#: Written into a spill that had to be cut. The marker says so as well; this is
#: for whoever opens the file directly.
SPILL_CLIPPED_NOTE = "\n\n[spill clipped: output exceeded the per-file limit]"

_SAFE_SEGMENT = re.compile(r"[^A-Za-z0-9_-]")

#: Permissions, which differ by execution mode because the reader does.
#:
#: In host mode the agent *is* this process: same uid, so the tightest bits work
#: and the spill stays private to the account that owns the data. That is the
#: default configuration and the one that should not be weakened.
#:
#: In sandbox mode the reader is a container running as a fixed uid 1000 that
#: need not match the service's, and bind mounts preserve numeric ownership — so
#: the file has to be world-readable or the marker points at something the agent
#: cannot open. That is a real cost: on a multi-user host any local account can
#: then read raw tool output. It buys the feature in sandbox mode and nothing
#: else, and the way out is ownership or a dedicated mount, not more permission
#: bits — three rounds of tightening and loosening these constants is what
#: showed that the bits are the wrong instrument.
#:
#: Applied with fchmod rather than as creation flags: umask subtracts from a
#: creation mode and never from fchmod, and the descriptor is already pinned so
#: nothing can be swapped underneath it.
_PRIVATE_DIR_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600
_SHARED_DIR_MODE = 0o755
_SHARED_FILE_MODE = 0o644

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
    """A directory name for this chat, safe to place in a path.

    Prefixed by execution mode, because the mode decides the directory's
    permissions and a chat can switch between them. Sharing one directory meant
    a host spill chmodded it 0700 and every sandbox path already advertised
    from it stopped being readable — the mode of the most recent spill
    retroactively deciding whether older ones could be opened. Separate leaves
    cannot contradict each other.
    """
    raw = str(getattr(deps, "chat_id", "") or "shared")
    safe = _SAFE_SEGMENT.sub("-", raw)[:64] or "shared"
    prefix = "sandbox" if getattr(deps, "sandbox_enabled", True) else "host"
    return f"{prefix}-{safe}"


def _force_mode(fd: int, mode: int) -> None:
    """Set the mode the creation flags only requested.

    umask subtracts from a creation mode and never from fchmod, so this is the
    difference between the intended permissions and whatever the service happens
    to have been started with.
    """
    # os.fchmod does not exist on Windows before 3.13, and AttributeError is not
    # an OSError — uncaught, it escaped before fdopen took ownership of the
    # descriptor, so every oversized result leaked a handle and wrote nothing.
    setter = getattr(os, "fchmod", None)
    if setter is None:
        return
    try:
        setter(fd, mode)
    except (OSError, NotImplementedError) as e:
        logger.debug(f"[overflow] could not set mode {oct(mode)}: {e}")


def _open_child_dir(name: str, parent_fd: int, dir_mode: int) -> int:
    """Open (creating if needed) a subdirectory, refusing to follow a symlink.

    Taken relative to *parent_fd* so a directory swapped for a symlink after the
    parent was opened cannot redirect the write.
    """
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        os.mkdir(name, dir_mode, dir_fd=parent_fd)
    except FileExistsError:
        pass
    fd = os.open(name, flags, dir_fd=parent_fd)
    _force_mode(fd, dir_mode)
    return fd


def _spill_by_path(
    payload: bytes, directory: Path, name: str, dir_mode: int, file_mode: int
) -> bool:
    """Write the spill without directory descriptors.

    For platforms where ``dir_fd`` is unsupported — Windows — which are also the
    ones with no bind-mounted sandbox writing into this tree, so the pinning it
    would buy has nothing to defend against. Keeping the fd-based code and
    merely passing ``dir_fd=None`` was not a fallback at all: ``os.open`` raises
    NotImplementedError there, which no ``except OSError`` catches, turning an
    oversized tool result into a failed tool call.
    """
    try:
        # Ancestors shared between modes, leaf private — see _spill_pinned.
        directory.parent.mkdir(mode=_SHARED_DIR_MODE, parents=True, exist_ok=True)
        try:
            directory.parent.chmod(_SHARED_DIR_MODE)
        except OSError:
            pass
        directory.mkdir(mode=dir_mode, exist_ok=True)
        try:
            directory.chmod(dir_mode)
        except OSError:
            pass
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        target = directory / name
        fd = os.open(target, flags, file_mode)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
        except BaseException:
            # fdopen owns the descriptor only once it returns; before that the
            # raw fd is ours to close, and a leaked handle per oversized result
            # exhausts the process.
            os.close(fd)
            raise
        # By path here rather than by descriptor: this branch exists for
        # platforms without dir_fd, which are also the ones that may lack
        # fchmod.
        try:
            target.chmod(file_mode)
        except OSError:
            pass
    except (OSError, NotImplementedError, ValueError) as e:
        logger.debug(f"[overflow] could not write spill: {e}")
        return False

    _prune_path(directory)
    _enforce_root_quota_path(directory.parent)
    return True


def _clip(text: str) -> tuple[bytes, bool]:
    """Encode *text*, cut to the per-file ceiling on a character boundary.

    Slicing the encoded bytes can land inside a multi-byte code point, and the
    resulting file is not valid UTF-8 — so the reader that was supposed to
    rescue the output fails to open it.
    """
    # Slice the string first. Encoding the whole thing to find out it is too
    # long allocates a second full-size copy while the original result is still
    # live, so a command that prints hundreds of MiB costs that twice over to
    # write five. A UTF-8 character is at least one byte, so the first
    # OVERFLOW_MAX_FILE_BYTES characters always contain at least that many
    # bytes — enough to fill the file — and at most four times as many, which
    # is the bound this buys.
    head = text[:OVERFLOW_MAX_FILE_BYTES]
    payload = head.encode("utf-8", "replace")
    if len(payload) <= OVERFLOW_MAX_FILE_BYTES and len(head) == len(text):
        return payload, False

    note = SPILL_CLIPPED_NOTE.encode("utf-8")
    keep = OVERFLOW_MAX_FILE_BYTES - len(note)
    # Decode-then-encode so the cut lands on a character boundary: slicing
    # encoded bytes can split a code point, and the file the reader was meant
    # to open would not be valid UTF-8.
    return payload[:keep].decode("utf-8", "ignore").encode("utf-8") + note, True


def _prune_path(directory: Path) -> None:
    """The path-based twin of _prune_fd, for platforms without dir_fd."""
    try:
        entries = []
        for path in directory.glob("*.txt"):
            try:
                stat = path.stat()
            except OSError:
                continue
            entries.append((stat.st_mtime, stat.st_size, path))
    except OSError:
        return

    entries.sort(reverse=True)
    cutoff = time.time() - OVERFLOW_TTL_SECONDS
    running = 0
    for index, (mtime, size, path) in enumerate(entries):
        drop = (
            index >= OVERFLOW_MAX_FILES
            or mtime < cutoff
            or running + size > OVERFLOW_MAX_TOTAL_BYTES
        )
        try:
            if drop:
                path.unlink(missing_ok=True)
            else:
                running += size
        except OSError:
            continue


def _enforce_root_quota_fd(root_fd: int) -> int:
    """Hold the deployment-wide ceiling across every chat directory.

    Separate from the per-chat prune because the two answer different
    questions, and leaving this one to the hourly sweep meant a burst of chats
    could sit above the root ceiling for an hour — long enough to fill a volume
    that every directory was individually respecting.

    Returns the number of files removed.
    """
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    survivors: list[tuple[float, int, str, str]] = []
    try:
        for entry in os.scandir(root_fd):
            if not entry.is_dir(follow_symlinks=False):
                continue
            try:
                chat_fd = os.open(entry.name, flags, dir_fd=root_fd)
            except OSError:
                continue
            try:
                for kept in os.scandir(chat_fd):
                    try:
                        stat = kept.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    survivors.append(
                        (stat.st_mtime, stat.st_size, entry.name, kept.name)
                    )
            finally:
                os.close(chat_fd)
    except OSError:
        return 0

    # Newest first, so what goes is least likely to be referenced by a live
    # conversation.
    survivors.sort(reverse=True)
    removed = 0
    running = 0
    for _mtime, size, chat_name, file_name in survivors:
        if running + size <= OVERFLOW_MAX_ROOT_BYTES:
            running += size
            continue
        try:
            chat_fd = os.open(chat_name, flags, dir_fd=root_fd)
        except OSError:
            continue
        try:
            os.unlink(file_name, dir_fd=chat_fd)
            removed += 1
        except OSError:
            pass
        finally:
            os.close(chat_fd)
    return removed


def _enforce_root_quota_path(root: Path) -> int:
    """The path-based twin of _enforce_root_quota_fd."""
    survivors: list[tuple[float, int, Path]] = []
    try:
        for chat_dir in root.iterdir():
            if not chat_dir.is_dir() or chat_dir.is_symlink():
                continue
            for path in chat_dir.glob("*.txt"):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                survivors.append((stat.st_mtime, stat.st_size, path))
    except OSError:
        return 0

    survivors.sort(reverse=True)
    removed = 0
    running = 0
    for _mtime, size, path in survivors:
        if running + size <= OVERFLOW_MAX_ROOT_BYTES:
            running += size
            continue
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            continue
    return removed


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


def _spill_pinned(
    payload: bytes,
    shared_host: Path,
    chat: str,
    name: str,
    dir_mode: int,
    file_mode: int,
) -> bool:
    """Write the spill with every directory on the path pinned.

    Resolving a path and then using it is a race the agent can win: it may
    replace a directory between the two. Each step is therefore taken relative
    to a descriptor already opened with O_NOFOLLOW, so a swap after resolution
    cannot redirect the write — or the prune that follows it, which unlinks.
    """
    root_fd = overflow_fd = chat_fd = None
    try:
        shared_host.mkdir(parents=True, exist_ok=True)
        root_fd = os.open(shared_host, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        # The mount root as well. Forcing the mode on .overflow, the chat
        # directory and the file, but not on the directory they all sit inside,
        # leaves a 0700 root under umask 0077 — every descendant correct and
        # none of them reachable. /shared is the sandbox's own mount and has to
        # be traversable by it regardless; a 0700 root breaks memory too, not
        # only spills.
        # The mount root and .overflow are shared between execution modes, so
        # their mode cannot depend on which one is spilling right now: a host
        # spill setting them 0700 would make every path already advertised to a
        # sandbox container unreadable until some later sandbox spill happened
        # to set them back. Traversal is not readability — the chat directory
        # below still carries the private mode.
        _force_mode(root_fd, _SHARED_DIR_MODE)
        overflow_fd = _open_child_dir(".overflow", root_fd, _SHARED_DIR_MODE)
        chat_fd = _open_child_dir(chat, overflow_fd, dir_mode)

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(name, flags, file_mode, dir_fd=chat_fd)
        except OSError as e:
            if e.errno in (errno.EEXIST, errno.ELOOP):
                logger.warning(f"[overflow] refusing to write over {name}: {e}")
            else:
                logger.debug(f"[overflow] could not create spill: {e}")
            return False

        try:
            _force_mode(fd, file_mode)
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
        except OSError as e:
            logger.debug(f"[overflow] could not write spill: {e}")
            try:
                os.unlink(name, dir_fd=chat_fd)
            except OSError:
                pass
            return False

        _prune_fd(chat_fd)
        # And the root ceiling, here rather than only on the hourly timer: a
        # burst across many chats stays within every per-chat allowance while
        # the deployment total runs away.
        _enforce_root_quota_fd(overflow_fd)
        return True
    except OSError as e:
        logger.debug(f"[overflow] no spill directory: {e}")
        return False
    finally:
        for handle_fd in (chat_fd, overflow_fd, root_fd):
            if handle_fd is not None:
                try:
                    os.close(handle_fd)
                except OSError:
                    pass


def spill_overflow(text: str, *, deps: Any, kind: str = "output") -> Optional[Spill]:
    """Clip *text* and write it somewhere this chat can read it."""
    payload, clipped = _clip(text)
    return _spill_payload(payload, clipped, deps=deps, kind=kind)


def _spill_payload(
    payload: bytes, clipped: bool, *, deps: Any, kind: str = "output"
) -> Optional[Spill]:
    """Write an already-bounded *payload*; return where it went.

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

    # The canonical shared directory, not whatever /shared currently maps to.
    #
    # A custom volume can target /shared, and PathResolver gives that mapping
    # priority — so resolving it would write .overflow into the user's own
    # directory, force-chmod it 0755, and leave the files somewhere the sweep
    # (which knows only the canonical path) never looks. Deriving the root from
    # config keeps the writer and the collector talking about one directory.
    from suzent.config import CONFIG

    shared_host = Path(CONFIG.sandbox_data_path) / "shared"

    # In sandbox mode the agent reaches it as /shared — unless that mount has
    # been redirected, in which case there is no path to advertise and the plain
    # marker is the honest answer.
    if getattr(deps, "sandbox_enabled", True):
        try:
            mapped = Path(resolver.resolve("/shared")).resolve()
        except Exception as e:
            logger.debug(f"[overflow] no shared root: {e}")
            return None
        if mapped != shared_host.resolve():
            logger.debug(
                "[overflow] /shared is remapped by a custom volume; "
                "truncating without a pointer"
            )
            return None

    chat = _chat_segment(deps)
    name = f"{kind}-{secrets.token_hex(16)}.txt"

    sandboxed = bool(getattr(deps, "sandbox_enabled", True))
    dir_mode = _SHARED_DIR_MODE if sandboxed else _PRIVATE_DIR_MODE
    file_mode = _SHARED_FILE_MODE if sandboxed else _PRIVATE_FILE_MODE

    if not _HAVE_DIR_FD:
        if not _spill_by_path(
            payload, shared_host / ".overflow" / chat, name, dir_mode, file_mode
        ):
            return None
    elif not _spill_pinned(payload, shared_host, chat, name, dir_mode, file_mode):
        return None

    if getattr(deps, "sandbox_enabled", True):
        return Spill(f"{OVERFLOW_VIRTUAL_DIR}/{chat}/{name}", clipped)
    return Spill(str(shared_host / ".overflow" / chat / name), clipped)


#: How often the sweep runs while the service is up.
#:
#: The root quota and the retention window are only enforced where the sweep
#: reaches. Running it once at startup left both unenforced for the lifetime of
#: a long-lived process: a chat's last spill outlives its advertised window, and
#: the deployment-wide total is never checked at all, because a write only ever
#: prunes its own chat's directory.
OVERFLOW_SWEEP_INTERVAL_SECONDS = 60 * 60


async def sweep_overflow_periodically() -> None:
    """Keep the bounds enforced for as long as the service runs."""
    while True:
        try:
            await asyncio.sleep(OVERFLOW_SWEEP_INTERVAL_SECONDS)
            await asyncio.to_thread(sweep_overflow)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - a sweep failure must not end the loop
            logger.warning(f"[overflow] periodic sweep failed: {e}")


#: How long the caller waits for a spill before giving up on it.
#:
#: to_thread frees the loop and bounds nothing: a wedged volume would otherwise
#: hold reminder construction, or a tool result that has already succeeded, for
#: as long as the storage takes. Spilling is best-effort, so it gets a deadline
#: and the plain marker on expiry.
SPILL_TIMEOUT_SECONDS = 2.0

#: Concurrent spill workers allowed at once.
#:
#: A timed-out spill is abandoned, not cancelled — Python cannot kill a thread —
#: so permanently wedged storage means every oversized result leaves another
#: worker parked forever. Without a ceiling those accumulate until the process
#: runs out of threads and takes otherwise healthy tool calls down with it. At
#: saturation a spill is skipped rather than queued, because queueing behind
#: wedged work is how a transient stall becomes a permanent one.
_SPILL_THREADS = 4
_spill_slots = threading.Semaphore(_SPILL_THREADS)


def spill_overflow_bounded(
    text: str, *, deps: Any, kind: str = "output"
) -> Optional[Spill]:
    """The synchronous caller's version of the same deadline.

    A sync tool runs on a worker rather than the loop, so a wedged volume does
    not stall other chats — but it does hold a tool call that has *already
    succeeded*, which is the part worth bounding. Bounding only the async path
    left the two halves of one rule disagreeing, which is how most of this
    file's defects have looked.

    The thread is a daemon and is never joined past the deadline: it cannot be
    cancelled, so a late write simply lands in the spill directory and is
    collected by the sweep like any other file.
    """
    # Clipped here, in the caller, before any worker can capture it.
    #
    # An abandoned worker lives as long as the wedged storage does, so handing
    # it the original string means holding the whole of a hundreds-of-megabyte
    # result for that entire time. The semaphore bounds threads, not bytes; four
    # such workers are four copies of the largest output the process has seen.
    payload, clipped = _clip(text)

    if not _spill_slots.acquire(blocking=False):
        logger.warning(
            "[overflow] spill workers saturated; truncating without a pointer"
        )
        return None

    result: list[Optional[Spill]] = [None]

    def _worker() -> None:
        try:
            result[0] = _spill_payload(payload, clipped, deps=deps, kind=kind)
        finally:
            _spill_slots.release()

    thread = threading.Thread(target=_worker, name="overflow-spill", daemon=True)
    try:
        thread.start()
    except BaseException as e:
        # The worker's finally is what returns the slot, so a thread that never
        # starts never gives it back — four of those and spilling is off for the
        # life of the process. And a spill failure must never fail the tool call
        # that produced the output.
        _spill_slots.release()
        logger.warning(f"[overflow] could not start a spill worker: {e}")
        return None
    thread.join(timeout=SPILL_TIMEOUT_SECONDS)
    if thread.is_alive():
        logger.warning(
            f"[overflow] spill exceeded {SPILL_TIMEOUT_SECONDS}s — truncating "
            f"without a pointer"
        )
        return None
    return result[0]


async def spill_overflow_async(
    text: str, *, deps: Any, kind: str = "output"
) -> Optional[Spill]:
    """Spill without holding the event loop, and without waiting forever.

    Up to 5 MiB of write plus a directory scan; inline, that stalls every other
    chat the loop is serving. Off-loop but unbounded, a slow volume costs the
    caller instead — and the caller is either a reminder being built or a tool
    call that has already done its work. Losing the pointer beats losing
    either.

    The thread is not cancellable, so a timed-out write finishes in the
    background; it lands in the spill directory and is collected by the sweep
    like any other file.
    """
    # Through the same bounded worker as the sync path, not a bare to_thread: an
    # abandoned write on the default executor occupies one of its threads
    # forever, and that executor is shared with everything else that offloads.
    #
    # Still wrapped in a deadline, because that shared executor can be saturated
    # by unrelated work — the coroutine would then sit queued, never reaching
    # the join that was supposed to bound it. Routing through the bounded pool
    # is what made this necessary and is exactly when I removed it.
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(spill_overflow_bounded, text, deps=deps, kind=kind),
            timeout=SPILL_TIMEOUT_SECONDS * 2,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "[overflow] spill did not start in time — truncating without a pointer"
        )
        return None


def _sweep_by_path(root: Path) -> None:
    """Retention and the root quota without directory descriptors."""
    swept = 0
    for chat_dir in root.iterdir():
        if not chat_dir.is_dir() or chat_dir.is_symlink():
            continue
        try:
            before = len(list(chat_dir.glob("*.txt")))
            _prune_path(chat_dir)
            swept += before - len(list(chat_dir.glob("*.txt")))
            if not any(chat_dir.iterdir()):
                chat_dir.rmdir()
        except OSError:
            continue

    swept += _enforce_root_quota_path(root)

    if swept:
        logger.info(f"[overflow] swept {swept} stale spill(s)")


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

    if not _HAVE_DIR_FD:
        # The same split the write path makes. Having only spill_overflow()
        # choose an implementation left the sweep calling dir_fd operations on a
        # platform without them, so retention and the root quota simply did not
        # run there — the third time in this file that hardening one path and
        # not its twin left the twin broken.
        _sweep_by_path(root)
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

        swept += _enforce_root_quota_fd(root_fd)
    except OSError:
        pass
    finally:
        os.close(root_fd)

    if swept:
        logger.info(f"[overflow] swept {swept} stale spill(s)")
