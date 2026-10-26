"""Background half of silent updates.

The backend periodically asks the standalone updater to stage the latest
release (`suzent update --prefetch`): every download happens here, while
Suzent keeps running. Installing the staged release is a few seconds of
switching that happens when nobody is using Suzent -- the desktop app does it
when it exits or next starts; an unattended service does it here, in the small
hours, once every chat has been quiet for a while.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from suzent.logger import get_logger

logger = get_logger(__name__)

FIRST_CHECK_DELAY_SECONDS = 5 * 60
TICK_SECONDS = 15 * 60
PREFETCH_INTERVAL_SECONDS = 6 * 60 * 60
QUIET_HOURS = range(3, 5)
IDLE_SECONDS = 30 * 60


def _release_install(root: Path) -> bool:
    """Only bootstrapped release installs update themselves."""
    return (root / ".suzent-bootstrap-complete").exists() and (
        root / ".suzent" / "release-tag"
    ).exists()


def _disabled_by_user(root: Path) -> bool:
    if os.environ.get("SUZENT_AUTO_UPDATE", "").strip().lower() in {
        "0",
        "false",
        "off",
    }:
        return True
    try:
        return (root / ".suzent" / "auto-update").read_text(
            encoding="utf-8"
        ).strip() == "off"
    except OSError:
        return False


def _has_staged_update(root: Path) -> bool:
    return (root / ".suzent" / "staged-update.json").exists()


def agents_idle(now: float, idle_seconds: float = IDLE_SECONDS) -> bool:
    """Return whether no chat, stream or subagent has run for `idle_seconds`."""
    from suzent.core.run_state import _chat_states
    from suzent.core.stream_registry import stream_controls
    from suzent.core.subagent_runner import list_active_tasks

    if list_active_tasks():
        return False
    if any(
        not control.completed_event.is_set() for control in stream_controls.values()
    ):
        return False
    for state in _chat_states.values():
        if state.active_task is not None and not state.active_task.done():
            return False
        if now - state.last_activity < idle_seconds:
            return False
    return True


def desktop_app_running() -> bool:
    """The updater replaces the desktop binary, so it must not be open."""
    import psutil

    for process in psutil.process_iter(["name"]):
        name = (process.info.get("name") or "").lower()
        if name.startswith("suzent-ui"):
            return True
    return False


def should_apply_in_service(root: Path, moment: datetime) -> bool:
    return (
        _has_staged_update(root)
        and moment.hour in QUIET_HOURS
        and agents_idle(moment.timestamp())
        and not desktop_app_running()
    )


async def _run_cli(root: Path, *args: str) -> str:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "suzent.cli",
        *args,
        cwd=str(root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "SUZENT_SKIP_UPDATE_CHECK": "1"},
    )
    output, _ = await process.communicate()
    lines = output.decode("utf-8", errors="replace").strip().splitlines()
    return lines[-1] if lines else f"exit {process.returncode}"


async def run_auto_update(root: Path, *, service: bool) -> None:
    """Keep the latest release staged; in service mode, also install it."""
    if not _release_install(root):
        return
    await asyncio.sleep(FIRST_CHECK_DELAY_SECONDS)
    last_prefetch = 0.0
    while True:
        try:
            if not _disabled_by_user(root):
                if time.time() - last_prefetch >= PREFETCH_INTERVAL_SECONDS:
                    last_prefetch = time.time()
                    logger.info(
                        "Auto-update: {}", await _run_cli(root, "update", "--prefetch")
                    )
                if service and should_apply_in_service(root, datetime.now()):
                    logger.info(
                        "Auto-update: {}",
                        await _run_cli(root, "update", "--apply-staged"),
                    )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning("Auto-update check failed: {}", error)
        await asyncio.sleep(TICK_SECONDS)
