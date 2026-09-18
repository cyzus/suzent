"""Keep the served web UI bundle in step with the frontend source.

``src/suzent/webui/`` is a build artifact, not source: nothing in the normal
edit-and-refresh loop regenerates it, so a source checkout will happily serve a
bundle from weeks ago and give no sign that it is doing so. That failure is
quiet and expensive -- the code is right, the page is old, and the obvious
conclusion is that the change did not work.

So the backend checks, and rebuilds when the frontend has moved on. This only
ever happens in a source checkout that has ``frontend/`` and npm: an installed
wheel carries a prebuilt bundle and no way to build one, and finds nothing to do
here. Rebuilds run on a worker thread and never block a request; the old bundle
is served until the new one is staged.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from suzent.logger import logger

#: Directories inside ``frontend/`` that are outputs or caches, not inputs.
_IGNORED_DIRS = frozenset({"node_modules", "dist", ".vite", "coverage"})

#: How often the staleness scan may run. A page load triggers a check, and a
#: browser hitting refresh should not mean walking the tree once per asset.
_CHECK_INTERVAL_SECONDS = 2.0

_lock = threading.Lock()
_building = False
_last_checked_at = 0.0
_last_failure_mtime: float | None = None


def _project_root() -> Path:
    from suzent.config import PROJECT_DIR

    return Path(PROJECT_DIR)


def _frontend_dir() -> Path | None:
    """The frontend source tree, if this install is a source checkout."""
    frontend = _project_root() / "frontend"
    return frontend if (frontend / "package.json").is_file() else None


def _builder_script() -> Path | None:
    script = _project_root() / "scripts" / "build_webui.py"
    return script if script.is_file() else None


def auto_build_enabled() -> bool:
    """Whether this process may rebuild the bundle on its own.

    ``SUZENT_AUTO_BUILD_WEBUI=0`` turns it off for anyone who would rather run
    the build themselves -- and for a checkout whose npm is slow enough that a
    surprise build is worse than a stale page.
    """
    setting = os.getenv("SUZENT_AUTO_BUILD_WEBUI", "").strip().lower()
    if setting in {"0", "false", "no"}:
        return False
    # Importing the server is enough to reach this code, and a test suite must
    # not spend a minute in npm because it built an app object.
    if "pytest" in sys.modules:
        return False
    return (
        _frontend_dir() is not None
        and _builder_script() is not None
        and shutil.which("npm") is not None
    )


def _newest_source_mtime(frontend: Path) -> float:
    newest = 0.0
    for root, dirs, files in os.walk(frontend):
        dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS and not d.startswith(".")]
        for name in files:
            try:
                mtime = (Path(root) / name).stat().st_mtime
            except OSError:
                continue
            if mtime > newest:
                newest = mtime
    return newest


def _staleness(frontend: Path) -> tuple[bool, float]:
    """Whether a rebuild is due, and the source mtime that decided it."""
    from suzent.webui import INDEX_FILE

    newest = _newest_source_mtime(frontend)
    try:
        built_at = INDEX_FILE.stat().st_mtime
    except OSError:
        return True, newest  # Nothing staged yet: there is something to build.
    if newest <= built_at:
        return False, newest
    # A build that failed leaves the source newer than the bundle forever, and
    # retrying it on every page load would turn one broken build into a loop.
    return newest != _last_failure_mtime, newest


def bundle_is_stale() -> bool:
    """Whether the frontend has changed since the bundle was staged.

    Compared against the bundle's own ``index.html``, which every build
    rewrites.
    """
    frontend = _frontend_dir()
    return False if frontend is None else _staleness(frontend)[0]


def _run_build(frontend: Path, script: Path, source_mtime: float) -> None:
    global _building, _last_failure_mtime

    started = time.monotonic()
    logger.info("Web UI bundle is out of date; rebuilding from {}", frontend)
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(_project_root()),
            capture_output=True,
            # Not text=True: that decodes with the console's locale codec, and
            # npm's output is UTF-8 whatever the console thinks. On a CJK
            # Windows the reader thread dies mid-build and takes the error
            # message we would have logged with it.
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        if result.returncode == 0:
            logger.info(
                "Web UI rebuilt in {:.0f}s; refresh the page to pick it up",
                time.monotonic() - started,
            )
        else:
            _last_failure_mtime = source_mtime
            tail = (result.stderr or result.stdout or "").strip().splitlines()[-10:]
            logger.warning(
                "Web UI rebuild failed ({}); still serving the previous bundle:\n{}",
                result.returncode,
                "\n".join(tail),
            )
    except (OSError, subprocess.SubprocessError) as exc:
        _last_failure_mtime = source_mtime
        logger.warning("Web UI rebuild could not run: {}", exc)
    finally:
        with _lock:
            _building = False


def rebuild_if_stale() -> bool:
    """Start a rebuild when one is due. Returns whether one was started.

    Safe to call from a request handler: the scan is rate-limited, the build
    runs on its own thread, and a second call while one is running is a no-op.
    """
    global _building, _last_checked_at

    if not auto_build_enabled():
        return False

    now = time.monotonic()
    with _lock:
        if _building or now - _last_checked_at < _CHECK_INTERVAL_SECONDS:
            return False
        _last_checked_at = now

    frontend = _frontend_dir()
    script = _builder_script()
    if frontend is None or script is None:
        return False
    stale, source_mtime = _staleness(frontend)
    if not stale:
        return False

    with _lock:
        if _building:
            return False
        _building = True

    threading.Thread(
        target=_run_build,
        args=(frontend, script, source_mtime),
        name="webui_rebuild",
        daemon=True,
    ).start()
    return True
