"""Somewhere to put the part of an output that did not fit.

A cap keeps a single tool result from swallowing the context window, but the
tail it removes is usually the part someone wanted: the failing assertion at the
end of a test run, the last hundred lines of a build log. Truncating to a marker
tells the model that content is missing without giving it any way to read it.

So the full text is written to a file and the marker carries the path.

One known limitation: a spill with no newlines — minified JSON, one enormous
value — cannot be read past the first chunk, because the read tool pages by
whole lines and that single line is itself over the cap. The pointer is honest
but unusable for that shape of output; fixing it means byte-range reads in
ReadFileTool, which is that tool's change to make.

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
import hashlib
import math
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from types import SimpleNamespace
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

#: How often the sweep runs while the service is up.
#:
#: The root quota and the retention window are only enforced where the sweep
#: reaches. Running it once at startup left both unenforced for the lifetime of
#: a long-lived process: a chat's last spill outlives its advertised window, and
#: the deployment-wide total is never checked at all, because a write only ever
#: prunes its own chat's directory.
OVERFLOW_SWEEP_INTERVAL_SECONDS = 60 * 60

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

#: How long a spill is immune from pruning after it is written.
#:
#: Publication and advertisement are not one step: the file is renamed into
#: place, and only then does the pointer reach the caller. Another chat's prune
#: or the sweep can run in between, and on a coarse-mtime filesystem — or after
#: the clock steps back — the new file need not sort as newest, so quota
#: pressure could delete the very path about to be returned.
#:
#: A grace period closes that without coordination between the writer, the other
#: writers and the sweep, which is what every attempt to synchronise them cost
#: in this file. It buys a bounded overshoot: whatever is written in a minute.
OVERFLOW_GRACE_SECONDS = 60

#: How far ahead of the clock an mtime may sit and still be believed.
#:
#: Grace is a window, not a lower bound. If the host's clock steps backwards —
#: an NTP correction, a VM resuming from a snapshot — every file published
#: before the step is stamped in the future, and a one-sided ``mtime >= now -
#: 60`` treats all of them as newborn for the whole rollback interval, which
#: can be hours. A burst caught by that window sits above both ceilings until
#: the clock catches up. Bounding the window on both sides costs one
#: comparison and keeps the overshoot at a minute's worth of writes; the slack
#: absorbs coarse filesystem timestamps and small NFS skew.
OVERFLOW_CLOCK_SKEW_SECONDS = 5

#: Suffix a spill wears while it is being written.
#:
#: Scans match ``*.txt``, so a partial file is invisible to them: the sweep or
#: another chat's prune cannot select a half-written spill for deletion — and on
#: POSIX that deletion succeeds silently against the open inode, leaving an
#: advertised path with no file behind it. The rename is atomic, so the name
#: appears only once the content is complete.
PARTIAL_SUFFIX = ".part"

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
    """Where the overflow went, and whether all of it got there.

    ``host_path`` is the file on disk; ``path`` is what the agent is told, which
    differs in sandbox mode. Both are needed because a spill that finishes after
    its caller gave up has to be removed, and only the host path can do that.
    """

    path: str
    clipped: bool
    host_path: Optional[str] = None


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
    # TTL plus the sweep interval, because deletion happens on a tick and not on
    # an alarm: a spill created just after one sweep is still inside the window
    # at the tick that follows its expiry, and goes on the one after that. An
    # advertised bound the ordinary schedule does not meet is the same defect as
    # the "full output" claim this marker already had to walk back.
    longest = OVERFLOW_TTL_SECONDS + OVERFLOW_SWEEP_INTERVAL_SECONDS
    return f"kept up to {longest // 3600}h"


def _implausibly_dated(mtime: float, now: float) -> bool:
    """True for a timestamp far enough ahead of the clock to be untrustworthy.

    A backward clock step leaves every already-published spill stamped in the
    future. Read literally, such a stamp is both forever young and forever
    short of the TTL cutoff, so the file outlives the retention the marker
    advertises by however long the rollback was. Treating it as undatable and
    expiring it keeps the promise; the alternative — believing it — cannot.
    """
    return mtime > now + OVERFLOW_CLOCK_SKEW_SECONDS


def _in_grace(mtime: float, now: float) -> bool:
    """True while a spill is too young to evict."""
    return not _implausibly_dated(mtime, now) and mtime >= now - OVERFLOW_GRACE_SECONDS


def _past_ttl(mtime: float, now: float) -> bool:
    """True once a spill has outlived its retention, or lost its datability."""
    return mtime < now - OVERFLOW_TTL_SECONDS or _implausibly_dated(mtime, now)


def _age_key(mtime: float, now: float) -> float:
    """The timestamp to sort a spill by, with undatable ones sorted oldest.

    The root scan orders newest-first and evicts from the tail, on the theory
    that the newest file is the one a live conversation is most likely to be
    holding a pointer to. A future-dated stamp defeats that theory exactly: a
    file left over from before a clock step sorts ahead of everything real, so
    it keeps its budget while genuinely current spills are evicted and their
    advertised pointers break. Sorting it as oldest puts it first in line
    instead, which is where a timestamp nobody can believe belongs.
    """
    return -math.inf if _implausibly_dated(mtime, now) else mtime


def _abandoned(mtime: float, now: float) -> bool:
    """True for a staged file old enough that no writer can still hold it.

    Deliberately blind to the rollback rule that governs published spills. A
    ``.part`` is not subject to the retention promise — nothing advertises it —
    and a clock step backwards mid-write would otherwise make an active
    writer's file look expired. Deleting it succeeds silently against the open
    inode on POSIX: the write finishes into nothing, the rename fails, and the
    caller gets no pointer at all. A future-dated staged file waits for the
    clock instead, which costs one stale file and no lost output.
    """
    return mtime < now - OVERFLOW_TTL_SECONDS


def _shared_root() -> Path:
    """The canonical shared directory, absolute.

    ``sandbox_data_path`` may be relative — the documented default is
    ``.suzent/sandbox`` — and a relative host path is worse than useless in a
    marker: PathResolver resolves relative paths against the *chat's* working
    directory, so the pointer would send the agent looking under its own cwd
    for a file written next to the server's. Absolute here, once, for the
    writer and the sweep alike.
    """
    from suzent.config import CONFIG

    return Path(CONFIG.sandbox_data_path).expanduser().resolve() / "shared"


def _overflow_root() -> Path:
    return _shared_root() / ".overflow"


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
    safe = _SAFE_SEGMENT.sub("-", raw) or "shared"
    prefix = "sandbox" if getattr(deps, "sandbox_enabled", True) else "host"
    # The digest is unconditional, because both ways of deriving a name are
    # many-to-one and a conditional only covers the one you thought of. A
    # truncation merges ids sharing a prefix; the sanitiser merges ids differing
    # only in characters it replaces — `a2a:local:a/b` and `a2a:local:a?b` both
    # become `a2a-local-a-b`. Merged chats share a quota and evict each other's
    # advertised spills.
    digest = hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:12]
    return f"{prefix}-{safe[:48]}-{digest}"


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
    payload: bytes,
    directory: Path,
    name: str,
    dir_mode: int,
    file_mode: int,
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
        staged = directory / (name + PARTIAL_SUFFIX)
        fd = os.open(staged, flags, file_mode)
        # Ownership transfers at fdopen and not before. Closing the raw number
        # after the `with` has already closed it would be a double close, and in
        # a threaded server another thread can be handed that same descriptor
        # number in between — so a failed spill write could close an unrelated
        # socket.
        handle = None
        try:
            handle = os.fdopen(fd, "wb")
        finally:
            if handle is None:
                os.close(fd)
        with handle:
            handle.write(payload)
        # By path here rather than by descriptor: this branch exists for
        # platforms without dir_fd, which are also the ones that may lack
        # fchmod.
        try:
            staged.chmod(file_mode)
        except OSError:
            pass
        staged.replace(directory / name)
    except (OSError, NotImplementedError, ValueError) as e:
        logger.debug(f"[overflow] could not write spill: {e}")
        # The descriptor-based path already does this. A half-written file that
        # was never advertised is pure litter, and this branch skips pruning, so
        # it sits there until the sweep.
        try:
            (directory / (name + PARTIAL_SUFFIX)).unlink(missing_ok=True)
        except OSError:
            pass
        return False

    return True


def _bound_chars(text: str) -> tuple[str, bool]:
    """The prefix worth keeping, and whether anything was left behind.

    A slice, deliberately: cheap, and it is all the caller needs to do. Holding
    only this bounds what an abandoned worker can retain, while the encoding —
    which allocates up to four bytes per character — happens on the worker
    where it cannot block the loop.

    A UTF-8 character is at least one byte, so the first OVERFLOW_MAX_FILE_BYTES
    characters always contain at least that many bytes, which is enough to fill
    the file.
    """
    head = text[:OVERFLOW_MAX_FILE_BYTES]
    return head, len(head) != len(text)


def _encode_bounded(head: str, dropped: bool) -> tuple[bytes, bool]:
    """Encode a bounded prefix and cut it to the byte ceiling."""
    payload = head.encode("utf-8", "replace")
    if len(payload) <= OVERFLOW_MAX_FILE_BYTES and not dropped:
        return payload, False

    note = SPILL_CLIPPED_NOTE.encode("utf-8")
    keep = OVERFLOW_MAX_FILE_BYTES - len(note)
    # Decode-then-encode so the cut lands on a character boundary: slicing
    # encoded bytes can split a code point, and the file the reader was meant
    # to open would not be valid UTF-8.
    return payload[:keep].decode("utf-8", "ignore").encode("utf-8") + note, True


def _clip(text: str) -> tuple[bytes, bool]:
    """Bound and encode in one step, for callers already off the event loop."""
    head, dropped = _bound_chars(text)
    return _encode_bounded(head, dropped)


def _prune_path(directory: Path, protect: Optional[str] = None) -> None:
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
    # A crash or a failed rename can leave a staged file behind. It is
    # invisible to every scan by design, so the sweep is the only thing that
    # will ever collect it.
    for stale in directory.glob(f"*{PARTIAL_SUFFIX}"):
        try:
            if _abandoned(stale.stat().st_mtime, time.time()):
                stale.unlink(missing_ok=True)
        except OSError:
            continue

    now = time.time()
    running = 0
    kept = 0
    for mtime, size, path in entries:
        over = (
            kept >= OVERFLOW_MAX_FILES
            or _past_ttl(mtime, now)
            or running + size > OVERFLOW_MAX_TOTAL_BYTES
        )
        protected = path.name == protect or _in_grace(mtime, now)
        try:
            if over and not protected:
                path.unlink(missing_ok=True)
                continue
        except OSError:
            # It is still on disk, so it still occupies a slot and its bytes.
            pass
        running += size
        kept += 1


def _enforce_root_quota_fd(
    root_fd: int, protect: Optional[tuple[str, str]] = None
) -> int:
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
                    # Completed spills only. A staged file belongs to a writer
                    # that still has it open; unlinking it succeeds on POSIX and
                    # the rename then fails, so the result loses its pointer for
                    # a file that was never counted against anyone's quota
                    # anyway. The other three scans filter; this one did not.
                    if not kept.name.endswith(".txt"):
                        continue
                    try:
                        stat = kept.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    survivors.append(
                        (
                            _age_key(stat.st_mtime, time.time()),
                            stat.st_size,
                            entry.name,
                            kept.name,
                        )
                    )
            finally:
                os.close(chat_fd)
    except OSError:
        return 0

    # Newest first, so what goes is least likely to be referenced by a live
    # conversation.
    survivors.sort(reverse=True)
    now = time.time()
    removed = 0
    running = 0
    for mtime, size, chat_name, file_name in survivors:
        # Counted whether or not it can be deleted: omitting fresh files from
        # the running total let a burst across chats exceed the deployment
        # ceiling entirely, which is the ceiling's whole purpose.
        protected = protect == (chat_name, file_name) or _in_grace(mtime, now)
        if running + size <= OVERFLOW_MAX_ROOT_BYTES or protected:
            running += size
            continue
        try:
            chat_fd = os.open(chat_name, flags, dir_fd=root_fd)
        except OSError:
            running += size
            continue
        try:
            os.unlink(file_name, dir_fd=chat_fd)
            removed += 1
        except OSError:
            running += size
        finally:
            os.close(chat_fd)
    return removed


def _enforce_root_quota_path(
    root: Path, protect: Optional[tuple[str, str]] = None
) -> int:
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
                survivors.append(
                    (_age_key(stat.st_mtime, time.time()), stat.st_size, path)
                )
    except OSError:
        return 0

    survivors.sort(reverse=True)
    now = time.time()
    removed = 0
    running = 0
    for mtime, size, path in survivors:
        protected = protect == (path.parent.name, path.name) or _in_grace(mtime, now)
        if running + size <= OVERFLOW_MAX_ROOT_BYTES or protected:
            running += size
            continue
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            running += size
    return removed


def _prune_fd(dir_fd: int, protect: Optional[str] = None) -> None:
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

    # Staged files are invisible to the scan above, so the sweep collects the
    # ones a crash or a failed rename left behind.
    try:
        for entry in os.scandir(dir_fd):
            if not entry.name.endswith(PARTIAL_SUFFIX):
                continue
            try:
                if _abandoned(entry.stat(follow_symlinks=False).st_mtime, time.time()):
                    os.unlink(entry.name, dir_fd=dir_fd)
            except OSError:
                continue
    except OSError:
        pass

    entries.sort(reverse=True)
    now = time.time()
    running = 0
    kept = 0
    for mtime, size, name in entries:
        # The ceiling counts what is being kept, not how far down the list an
        # entry sits. Counting positions charged a file for the entries above
        # it that were themselves deleted — one expired spill at the head was
        # enough to evict a valid one at the tail and break its pointer.
        over = (
            kept >= OVERFLOW_MAX_FILES
            or _past_ttl(mtime, now)
            or running + size > OVERFLOW_MAX_TOTAL_BYTES
        )
        # Undeletable is not the same as uncounted. Skipping fresh files
        # entirely let a burst sail past both ceilings — eleven maximum spills
        # exceed the per-chat limit while none is old enough to consider. They
        # consume budget like anything else; they are simply the ones that
        # displace older files rather than being displaced.
        protected = name == protect or _in_grace(mtime, now)
        try:
            if over and not protected:
                os.unlink(name, dir_fd=dir_fd)
                continue
        except OSError:
            # It is still on disk, so it still occupies a slot and its bytes.
            pass
        running += size
        kept += 1


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
        # Opened relative to its parent with no-follow, like every directory
        # below it. mkdir(exist_ok=True) accepts a symlink as an existing
        # directory, so a `shared` replaced by one would have been followed here
        # and every pinned step below would have been pinned to the wrong tree.
        flags = (
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        parent_fd = os.open(
            shared_host.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        try:
            root_fd = os.open(shared_host.name, flags, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
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
        staged = name + PARTIAL_SUFFIX
        try:
            fd = os.open(staged, flags, file_mode, dir_fd=chat_fd)
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
                os.unlink(staged, dir_fd=chat_fd)
            except OSError:
                pass
            return False

        try:
            os.rename(staged, name, src_dir_fd=chat_fd, dst_dir_fd=chat_fd)
        except OSError as e:
            logger.debug(f"[overflow] could not publish spill: {e}")
            try:
                os.unlink(staged, dir_fd=chat_fd)
            except OSError:
                pass
            return False

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


def _prune_now(deps: Any, protect: Optional[str] = None) -> None:
    """Apply the quotas after a write.

    Unconditional again, and that is the point of dropping the handshake: with
    nothing deleted out of band, a spill whose caller timed out is not a mistake
    to be undone — it is a retained file like any other, so pruning on its
    behalf is a legitimate retention decision rather than an eviction by
    something that is about to vanish.
    """
    root = _overflow_root()
    chat = _chat_segment(deps)
    try:
        if _HAVE_DIR_FD:
            flags = (
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            root_fd = os.open(root, flags)
            try:
                chat_fd = os.open(chat, flags, dir_fd=root_fd)
                try:
                    _prune_fd(chat_fd, protect)
                finally:
                    os.close(chat_fd)
                _enforce_root_quota_fd(root_fd, (chat, protect) if protect else None)
            finally:
                os.close(root_fd)
        else:
            _prune_path(root / chat, protect)
            _enforce_root_quota_path(root, (chat, protect) if protect else None)
    except OSError as e:
        logger.debug(f"[overflow] could not prune after a spill: {e}")


def _deps_snapshot(deps: Any) -> Any:
    """The three values a spill actually needs.

    An abandoned worker holds its closure for as long as the storage stays
    wedged, and AgentDeps carries the request's message history, repository
    context and caches. Four of those is far more than the bounded payload the
    slot limit was reasoning about.
    """
    return SimpleNamespace(
        path_resolver=getattr(deps, "path_resolver", None),
        sandbox_enabled=getattr(deps, "sandbox_enabled", True),
        chat_id=getattr(deps, "chat_id", ""),
    )


def spill_overflow(text: str, *, deps: Any, kind: str = "output") -> Optional[Spill]:
    """Clip *text* and write it somewhere this chat can read it.

    Prunes straight away: this entry point has no caller that can walk away
    mid-write, so acceptance is immediate. The bounded and async wrappers make
    that decision themselves and prune only once it goes their way.
    """
    payload, clipped = _clip(text)
    return _spill_payload(payload, clipped, deps=deps, kind=kind)


def _spill_payload(
    payload: bytes,
    clipped: bool,
    *,
    deps: Any,
    kind: str = "output",
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
    shared_host = _shared_root()

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

    # Checked before anything is written.
    #
    # A custom volume can mask /shared/.overflow or a directory under it, and
    # validating only afterwards meant the file was created and both quota
    # passes had run before the answer was discarded — so a chat with a masked
    # mount produced unreachable orphans on every oversized result, and its
    # pruning could evict spills other chats were still pointing at. Work not
    # worth doing is worth not doing before the side effects, not after.
    virtual: Optional[str] = None
    if sandboxed:
        virtual = f"{OVERFLOW_VIRTUAL_DIR}/{chat}/{name}"
        written = shared_host / ".overflow" / chat / name
        try:
            if Path(resolver.resolve(virtual)).resolve() != written.resolve():
                logger.debug(
                    "[overflow] a custom mount masks the spill path; "
                    "truncating without a pointer"
                )
                return None
        except Exception as e:
            logger.debug(f"[overflow] cannot verify the spill path: {e}")
            return None
    dir_mode = _SHARED_DIR_MODE if sandboxed else _PRIVATE_DIR_MODE
    file_mode = _SHARED_FILE_MODE if sandboxed else _PRIVATE_FILE_MODE

    if not _HAVE_DIR_FD:
        if not _spill_by_path(
            payload,
            shared_host / ".overflow" / chat,
            name,
            dir_mode,
            file_mode,
        ):
            return None
    elif not _spill_pinned(payload, shared_host, chat, name, dir_mode, file_mode):
        return None

    # The file just written is exempt: on a filesystem with coarse mtime, or
    # after the clock steps back, it need not sort ahead of the others, and a
    # directory already at quota would delete the very path about to be
    # advertised.
    _prune_now(deps, protect=name)

    written = shared_host / ".overflow" / chat / name
    if virtual is not None:
        return Spill(virtual, clipped, str(written))
    return Spill(str(written), clipped, str(written))


#: Held for the duration of a sweep, so a wedged one cannot be joined by the
#: next tick. There is nothing useful for a second concurrent sweep to do — it
#: would walk the same directories — and on storage that recovers after an
#: outage, an hour's worth of queued sweeps would all start at once.
_sweep_lock = threading.Lock()


def sweep_overflow_in_background() -> None:
    """Run one sweep on a thread the process can leave behind.

    Not to_thread: cancelling the coroutine does not stop the function, and the
    default executor's threads are joined at interpreter exit — so a sweep on a
    wedged filesystem would hold up shutdown itself, which is precisely what the
    cancellation added earlier was meant to prevent.
    """

    if not _sweep_lock.acquire(blocking=False):
        logger.debug("[overflow] a sweep is still running; skipping this tick")
        return

    def _guarded() -> None:
        # The caller's try/except cannot see a thread's exception, so moving the
        # sweep off the loop moved its failures out of reach of the handler that
        # was catching them — they surfaced as unhandled thread errors instead.
        try:
            sweep_overflow()
        except Exception as e:  # noqa: BLE001 - a sweep failure is not fatal
            logger.warning(f"[overflow] sweep failed: {e}")
        finally:
            _sweep_lock.release()

    try:
        threading.Thread(target=_guarded, name="overflow-sweep", daemon=True).start()
    except BaseException as e:
        _sweep_lock.release()
        logger.warning(f"[overflow] could not start the sweep: {e}")


async def sweep_overflow_periodically() -> None:
    """Keep the bounds enforced for as long as the service runs."""
    while True:
        try:
            await asyncio.sleep(OVERFLOW_SWEEP_INTERVAL_SECONDS)
            sweep_overflow_in_background()
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

    snapshot = _deps_snapshot(deps)
    result: list[Optional[Spill]] = [None]

    def _worker() -> None:
        try:
            result[0] = _spill_payload(payload, clipped, deps=snapshot, kind=kind)
        except BaseException as e:  # noqa: BLE001 - never fails its caller
            logger.debug(f"[overflow] spill failed: {e}")
        finally:
            _spill_slots.release()

    thread = threading.Thread(target=_worker, name="overflow-spill", daemon=True)
    try:
        thread.start()
    except BaseException as e:
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

    Sliced here, encoded and written on a thread of our own — not the shared
    default executor, whose queue keeps a cancelled submission's references
    until some worker dequeues it, and whose threads are joined at interpreter
    exit.

    A spill that misses the deadline is not chased. The caller gets the plain
    marker, the write finishes in the background, and the file it leaves is an
    ordinary spill: retained under the same TTL and quotas as any other, and
    collected by the sweep. Trying to hand the file back or delete it after the
    fact is what produced a run of races — every version of the handshake had a
    window between deciding and acting, because the caller, the loop and the
    worker cannot observe each other atomically.
    """
    head, dropped = _bound_chars(text)
    snapshot = _deps_snapshot(deps)

    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()

    def _deliver(value: Optional[Spill]) -> None:
        if not future.done():
            future.set_result(value)

    def _worker() -> None:
        spill = None
        try:
            payload, clipped = _encode_bounded(head, dropped)
            spill = _spill_payload(payload, clipped, deps=snapshot, kind=kind)
        except BaseException as e:  # noqa: BLE001 - a spill never fails its caller
            logger.debug(f"[overflow] spill failed: {e}")
        finally:
            _spill_slots.release()
        try:
            loop.call_soon_threadsafe(_deliver, spill)
        except RuntimeError:
            pass  # loop already closed; the sweep collects the file

    if not _spill_slots.acquire(blocking=False):
        logger.warning(
            "[overflow] spill workers saturated; truncating without a pointer"
        )
        return None

    try:
        threading.Thread(target=_worker, name="overflow-spill", daemon=True).start()
    except BaseException as e:
        _spill_slots.release()
        logger.warning(f"[overflow] could not start a spill worker: {e}")
        return None

    try:
        return await asyncio.wait_for(future, timeout=SPILL_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning(
            f"[overflow] spill exceeded {SPILL_TIMEOUT_SECONDS}s — truncating "
            f"without a pointer"
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
    root = _overflow_root()
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
