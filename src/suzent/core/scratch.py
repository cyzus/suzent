"""Size-capped cleanup for a project's scratch folder.

Scratch holds what the agent needs only for the task at hand: helper scripts,
downloads, reference clones. It is shared by every chat in the project, so it is
trimmed by total size rather than per chat: once it grows past the cap, the files
modified longest ago go first.
"""

import os
import threading
import time
from pathlib import Path

from suzent.logger import get_logger

logger = get_logger(__name__)

SCRATCH_DIRNAME = "scratch"
_PRUNE_INTERVAL_SECONDS = 3600.0

_last_pruned: dict[Path, float] = {}
_lock = threading.Lock()


def prune_scratch(directory: Path, max_bytes: int) -> int:
    """Delete the oldest files until ``directory`` fits in ``max_bytes``.

    Symlinks are removed as links and never followed, so nothing outside the
    folder can be reached or deleted. Returns the number of bytes freed.
    """
    root = directory.resolve()
    if not root.is_dir():
        return 0

    files: list[tuple[float, int, Path]] = []
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            path = Path(dirpath) / name
            try:
                stat = path.lstat()
            except OSError:
                continue
            size = 0 if path.is_symlink() else stat.st_size
            files.append((stat.st_mtime, size, path))
            total += size

    if total <= max_bytes:
        return 0

    freed = 0
    for _mtime, size, path in sorted(files, key=lambda item: item[0]):
        if total - freed <= max_bytes:
            break
        try:
            path.unlink()
        except OSError as exc:
            logger.debug("Could not remove scratch file {}: {}", path, exc)
            continue
        freed += size

    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        if Path(dirpath) != root and not dirnames and not filenames:
            try:
                os.rmdir(dirpath)
            except OSError:
                pass

    logger.info("Pruned {} bytes from scratch folder {}", freed, root)
    return freed


def schedule_scratch_prune(directory: Path, max_bytes: int) -> None:
    """Prune ``directory`` in the background, at most once an hour per folder."""
    if max_bytes <= 0:
        return
    key = directory.resolve()
    now = time.monotonic()
    with _lock:
        last = _last_pruned.get(key)
        if last is not None and now - last < _PRUNE_INTERVAL_SECONDS:
            return
        _last_pruned[key] = now

    def _run() -> None:
        try:
            prune_scratch(key, max_bytes)
        except Exception as exc:
            logger.warning("Scratch prune failed for {}: {}", key, exc)

    threading.Thread(target=_run, name="scratch-prune", daemon=True).start()
