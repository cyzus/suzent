"""
File-level change tracker for retry checkpoints.

Mirrors Claude Code's fileHistory.ts design:
- track_edit(path)   — call BEFORE writing; backs up the original file once
- make_snapshot()    — call AFTER a turn; checks for new changes, bumps versions
- apply_snapshot(snap) — restores files to a recorded snapshot state

Backup layout:
    sandbox/file-history/{chat_id}/{sha256(abs_path)[:16]}@v{n}

`backupFileName = None` means the file did not exist at that version.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class FileBackup:
    backup_name: Optional[str]  # None → file did not exist
    version: int
    backup_time: datetime


# Map of absolute-path string → FileBackup
FileSnapshot = Dict[str, FileBackup]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _backup_name(abs_path: str, version: int) -> str:
    h = hashlib.sha256(abs_path.encode()).hexdigest()[:16]
    return f"{h}@v{version}"


def _backup_dir(chat_id: str) -> Path:
    from suzent.config import CONFIG

    return Path(CONFIG.sandbox_data_path) / "file-history" / chat_id


def _backup_path(chat_id: str, backup_name: str) -> Path:
    return _backup_dir(chat_id) / backup_name


def _copy_file(src: Path, dst: Path) -> None:
    """Copy src → dst, creating parent dirs lazily."""
    try:
        shutil.copy2(src, dst)
    except FileNotFoundError:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _file_changed(abs_path: str, backup_name: str, chat_id: str) -> bool:
    """
    Return True if the live file differs from its backup.

    Fast path: size mismatch → changed immediately.
    Medium path: mtime of live file < mtime of backup → unchanged (backup is newer).
    Slow path: byte-by-byte comparison.
    """
    live = Path(abs_path)
    bak = _backup_path(chat_id, backup_name)

    try:
        live_st = live.stat()
    except OSError:
        # Live file disappeared → changed
        return True

    try:
        bak_st = bak.stat()
    except OSError:
        # Backup missing → treat as changed
        return True

    if live_st.st_size != bak_st.st_size:
        return True

    # If live mtime < backup mtime the live file predates the backup, so it
    # has not been modified since we made the backup.
    if live_st.st_mtime < bak_st.st_mtime:
        return False

    # Full content comparison
    return live.read_bytes() != bak.read_bytes()


# ---------------------------------------------------------------------------
# FileTracker
# ---------------------------------------------------------------------------


class FileTracker:
    """
    Per-chat, per-turn file change tracker.

    Lifecycle
    ---------
    1. Before writing a file → call ``track_edit(abs_path)``
    2. After the agent turn ends → call ``make_snapshot()``
    3. On retry → call ``apply_snapshot(snap)`` with a previously saved snapshot
    """

    def __init__(self, chat_id: str) -> None:
        self._chat_id = chat_id
        # abs_path → latest FileBackup recorded in the *current* pending snapshot
        self._pending: Dict[str, FileBackup] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def track_edit(self, abs_path: str) -> None:
        """
        Back up *abs_path* before it is written.

        Idempotent: if the file is already tracked in the current pending
        snapshot, the existing v1 backup is left untouched.
        """
        if abs_path in self._pending:
            return  # already captured for this turn

        live = Path(abs_path)
        version = 1
        bname: Optional[str] = None

        if live.exists():
            bname = _backup_name(abs_path, version)
            try:
                _copy_file(live, _backup_path(self._chat_id, bname))
                # Preserve permissions
                mode = live.stat().st_mode
                _backup_path(self._chat_id, bname).chmod(mode)
            except Exception as exc:
                logger.warning(f"[FileTracker] backup failed for {abs_path}: {exc}")
                bname = None  # treat as "didn't exist" on failure

        self._pending[abs_path] = FileBackup(
            backup_name=bname,
            version=version,
            backup_time=datetime.now(timezone.utc),
        )
        logger.debug(f"[FileTracker] tracked {abs_path} (exists={live.exists()})")

    def make_snapshot(self) -> FileSnapshot:
        """
        Finalise the pending snapshot for this turn.

        For any tracked file that changed since the v1 backup, create a new
        backup version.  Returns the snapshot dict (abs_path → FileBackup)
        and resets the pending set for the next turn.
        """
        snapshot: FileSnapshot = {}

        for abs_path, backup in self._pending.items():
            try:
                live = Path(abs_path)

                if not live.exists():
                    # File was deleted during this turn
                    snapshot[abs_path] = FileBackup(
                        backup_name=None,
                        version=backup.version,
                        backup_time=datetime.now(timezone.utc),
                    )
                    continue

                if backup.backup_name is not None and not _file_changed(
                    abs_path, backup.backup_name, self._chat_id
                ):
                    # Unchanged — reuse the existing backup entry
                    snapshot[abs_path] = backup
                    continue

                # File changed (or backup was None meaning it's newly created).
                # The v1 backup is already the pre-edit snapshot we need for
                # restore, so we just record the current state in the snapshot
                # without creating another copy.
                snapshot[abs_path] = backup

            except Exception as exc:
                logger.warning(
                    f"[FileTracker] make_snapshot error for {abs_path}: {exc}"
                )

        self._pending = {}
        return snapshot

    def reset(self) -> None:
        """Discard pending state without producing a snapshot."""
        self._pending = {}

    # ------------------------------------------------------------------
    # Static: apply a snapshot (restore files)
    # ------------------------------------------------------------------

    @staticmethod
    def apply_snapshot(chat_id: str, snapshot: FileSnapshot) -> list[str]:
        """
        Restore files to the state captured in *snapshot*.

        Returns the list of file paths that were actually changed on disk.
        """
        changed: list[str] = []

        for abs_path, backup in snapshot.items():
            try:
                live = Path(abs_path)

                if backup.backup_name is None:
                    # File should not exist — delete it if present
                    if live.exists():
                        live.unlink()
                        changed.append(abs_path)
                        logger.debug(
                            f"[FileTracker] apply: deleted {abs_path} (was new file)"
                        )
                    continue

                bak = _backup_path(chat_id, backup.backup_name)
                if not bak.exists():
                    logger.warning(
                        f"[FileTracker] apply: backup missing {bak}, skipping {abs_path}"
                    )
                    continue

                # Restore only if the live file actually differs
                if live.exists() and live.read_bytes() == bak.read_bytes():
                    continue

                # Restore
                live.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(bak, live)
                # Restore permissions
                bak_mode = bak.stat().st_mode
                live.chmod(bak_mode)
                changed.append(abs_path)
                logger.debug(
                    f"[FileTracker] apply: restored {abs_path} from {backup.backup_name}"
                )

            except Exception as exc:
                logger.warning(
                    f"[FileTracker] apply_snapshot error for {abs_path}: {exc}"
                )

        return changed

    # ------------------------------------------------------------------
    # Serialisation helpers (for DB storage)
    # ------------------------------------------------------------------

    @staticmethod
    def snapshot_to_json(snapshot: FileSnapshot) -> list[dict]:
        return [
            {
                "path": path,
                "backup_name": b.backup_name,
                "version": b.version,
                "backup_time": b.backup_time.isoformat(),
            }
            for path, b in snapshot.items()
        ]

    @staticmethod
    def snapshot_from_json(data: list[dict]) -> FileSnapshot:
        result: FileSnapshot = {}
        for entry in data:
            result[entry["path"]] = FileBackup(
                backup_name=entry.get("backup_name"),
                version=entry.get("version", 1),
                backup_time=datetime.fromisoformat(entry["backup_time"]),
            )
        return result
