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

import hashlib
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


def _prune(directory: Path) -> None:
    """Best-effort cleanup. A spill that cannot be pruned is still a spill."""
    try:
        files = sorted(
            (p for p in directory.glob("*.txt") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return

    cutoff = time.time() - OVERFLOW_TTL_SECONDS
    for index, path in enumerate(files):
        try:
            if index >= OVERFLOW_MAX_FILES or path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            continue


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

    digest = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:8]
    name = f"{kind}-{int(time.time())}-{digest}.txt"
    host_path = host_dir / name

    try:
        host_path.write_text(text, encoding="utf-8", errors="replace")
    except OSError as e:
        logger.debug(f"[overflow] could not write spill: {e}")
        return None

    _prune(host_dir)

    if getattr(deps, "sandbox_enabled", True):
        return f"{OVERFLOW_VIRTUAL_DIR}/{name}"
    return str(host_path)
