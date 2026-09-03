"""Somewhere to put the part of an output that did not fit.

A cap keeps a single tool result from swallowing the context window, but the
tail it removes is usually the part someone wanted: the failing assertion at the
end of a test run, the last hundred lines of a build log. Truncating to a marker
tells the model that content is missing without giving it any way to go and
read it.

So the full text is written to a file and the marker carries the path. The model
decides whether the rest is worth a read; nothing is silently lost either way.
"""

from __future__ import annotations

import errno
import os
import secrets
import time
from pathlib import Path
from typing import Any, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

#: Virtual home for spilled output. Under /shared rather than the project
#: workspace so it is not mistaken for the user's files, and so a spill from one
#: chat is readable by a sub-agent working on the same task.
OVERFLOW_VIRTUAL_DIR = "/shared/.overflow"

#: How long a spill file is worth keeping. Long enough that the model can read
#: it later in the same session, short enough that a week of build logs does not
#: accumulate on disk.
OVERFLOW_TTL_SECONDS = 24 * 60 * 60

#: Ceiling on files kept, whatever their age. A single runaway session can write
#: thousands; the TTL alone would not bound that until tomorrow.
OVERFLOW_MAX_FILES = 200

#: Ceiling on one spill. A foreground shell command reads its whole output into
#: memory and this writes all of it, so without a per-file bound a single
#: `cat` of something large lands on disk in full.
OVERFLOW_MAX_FILE_BYTES = 5 * 1024 * 1024

#: Ceiling on the directory. The count bound alone permits 200 files of any
#: size, which is not a bound on disk at all.
OVERFLOW_MAX_TOTAL_BYTES = 50 * 1024 * 1024

#: Appended when the spill itself had to be cut. Rare, and better said than not:
#: a file that silently holds part of the output is worse than the truncation it
#: was meant to relieve.
SPILL_CLIPPED_NOTE = "\n\n[spill clipped: output exceeded the per-file limit]"


def _prune(directory: Path) -> None:
    """Best-effort cleanup. A spill that cannot be pruned is still a spill.

    Bounded three ways, because each alone leaves a hole: age lets a burst sit
    until tomorrow, count permits 200 files of any size, and bytes alone would
    keep one ancient file forever.
    """
    try:
        files = sorted(
            (p for p in directory.glob("*.txt") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return

    cutoff = time.time() - OVERFLOW_TTL_SECONDS
    running_total = 0
    for index, path in enumerate(files):
        try:
            size = path.stat().st_size
            too_many = index >= OVERFLOW_MAX_FILES
            too_old = path.stat().st_mtime < cutoff
            too_big = running_total + size > OVERFLOW_MAX_TOTAL_BYTES
            if too_many or too_old or too_big:
                path.unlink(missing_ok=True)
                continue
            running_total += size
        except OSError:
            continue


def sweep_overflow() -> None:
    """Apply the retention bounds without needing a spill to trigger them.

    Pruning otherwise happens only on write, so the bounds hold exactly while
    output keeps overflowing and stop the moment it does not: the last spill of
    a session sits there until the next one, which may be never. Nothing else
    will collect it — this lives in the user's data directory, not in a temp
    directory the OS sweeps.

    Called at startup, which is also when yesterday's files are most likely to
    be both stale and forgotten.
    """
    from suzent.config import CONFIG

    directory = Path(CONFIG.sandbox_data_path) / "shared" / ".overflow"
    if not directory.is_dir():
        return
    before = len(list(directory.glob("*.txt")))
    _prune(directory)
    after = len(list(directory.glob("*.txt")))
    if before != after:
        logger.info(f"[overflow] swept {before - after} stale spill(s)")


def spill_overflow(text: str, *, deps: Any, kind: str = "output") -> Optional[str]:
    """Write *text* somewhere the agent can read it; return that path.

    Returns None when there is nowhere to write, which is not an error: the
    caller still truncates, it just cannot offer the rest. Losing the tail is
    better than failing the tool call that produced it.

    The path handed back is in the vocabulary of the agent's own filesystem —
    host paths in host mode, virtual in sandbox — because a path it cannot open
    is worse than no path at all: it invites a read that fails.
    """
    resolver = getattr(deps, "path_resolver", None)
    if resolver is None:
        return None

    try:
        host_dir = Path(resolver.resolve(OVERFLOW_VIRTUAL_DIR))
        host_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.debug(f"[overflow] no spill directory: {e}")
        return None

    payload = text.encode("utf-8", "replace")
    if len(payload) > OVERFLOW_MAX_FILE_BYTES:
        keep = OVERFLOW_MAX_FILE_BYTES - len(SPILL_CLIPPED_NOTE)
        payload = payload[:keep] + SPILL_CLIPPED_NOTE.encode("utf-8")

    # Unpredictable, and created without following anything already at the path.
    #
    # The name used to be derived from the output's own hash and the current
    # second, which a sandboxed agent can compute: pre-place a symlink there,
    # emit output that overflows, and the host process follows the link and
    # overwrites whatever it points at — no PathResolver check involved, since
    # the write is ours, not the agent's. O_EXCL refuses an existing path
    # (symlink included) and O_NOFOLLOW refuses to traverse one; the random name
    # means there is nothing to aim at in the first place.
    name = f"{kind}-{secrets.token_hex(16)}.txt"
    host_path = host_dir / name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)

    try:
        fd = os.open(host_path, flags, 0o600)
    except OSError as e:
        if e.errno in (errno.EEXIST, errno.ELOOP):
            logger.warning(f"[overflow] refusing to write over an existing path: {e}")
        else:
            logger.debug(f"[overflow] could not create spill: {e}")
        return None

    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
    except OSError as e:
        logger.debug(f"[overflow] could not write spill: {e}")
        try:
            host_path.unlink(missing_ok=True)
        except OSError:
            pass
        return None

    _prune(host_dir)

    if getattr(deps, "sandbox_enabled", True):
        return f"{OVERFLOW_VIRTUAL_DIR}/{name}"
    return str(host_path)
