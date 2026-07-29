"""
File-level change tracker for retry checkpoints.

Mirrors Claude Code's fileHistory.ts design:
- track_edit(path)   — call BEFORE writing; backs up the original file once
- make_snapshot()    — call AFTER a turn; checks for new changes, bumps versions
- apply_snapshot(snap) — restores files to a recorded snapshot state

Backup layout:
    sandbox/file-history/{chat_id}/{sha256(abs_path)[:16]}@{snapshot_id}-v{n}

`backupFileName = None` means the file did not exist at that version.
"""

from __future__ import annotations

import hashlib
import shutil
import uuid
from difflib import unified_diff
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
    after_hash: Optional[str] = None
    after_exists: bool = True
    diff: str = ""
    additions: int = 0
    deletions: int = 0


# Map of absolute-path string → FileBackup
FileSnapshot = Dict[str, FileBackup]


class FileRestoreConflictError(RuntimeError):
    """Raised when files changed after the agent turn and cannot be safely restored."""

    def __init__(self, paths: list[str]) -> None:
        self.paths = paths
        super().__init__(f"Refusing to overwrite {len(paths)} manually changed file(s)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _backup_name(abs_path: str, version: int, snapshot_id: str) -> str:
    h = hashlib.sha256(abs_path.encode()).hexdigest()[:16]
    return f"{h}@{snapshot_id}-v{version}"


def _display_path(abs_path: str) -> str:
    path = Path(abs_path)
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except (OSError, ValueError):
        normalized = abs_path.replace("\\", "/")
        for marker in ("/workspace/", "/workspaces/"):
            if marker in normalized:
                return normalized.split(marker, 1)[1]
        return normalized


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


def _content_hash(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _diff_metadata(before: Path | None, after: Path | None, display_path: str):
    try:
        before_lines = (
            before.read_text(encoding="utf-8", errors="strict").splitlines(True)
            if before and before.exists()
            else []
        )
        after_lines = (
            after.read_text(encoding="utf-8", errors="strict").splitlines(True)
            if after and after.exists()
            else []
        )
    except (OSError, UnicodeError):
        return "", 0, 0
    lines = list(
        unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{display_path}",
            tofile=f"b/{display_path}",
        )
    )
    additions = sum(
        1 for line in lines if line.startswith("+") and not line.startswith("+++")
    )
    deletions = sum(
        1 for line in lines if line.startswith("-") and not line.startswith("---")
    )
    return "".join(lines), additions, deletions


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
        self._snapshot_id = uuid.uuid4().hex[:12]
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
            bname = _backup_name(abs_path, version, self._snapshot_id)
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
                    before = (
                        _backup_path(self._chat_id, backup.backup_name)
                        if backup.backup_name
                        else None
                    )
                    diff, additions, deletions = _diff_metadata(
                        before, None, _display_path(abs_path)
                    )
                    snapshot[abs_path] = FileBackup(
                        backup_name=backup.backup_name,
                        version=backup.version,
                        backup_time=datetime.now(timezone.utc),
                        after_hash=None,
                        after_exists=False,
                        diff=diff,
                        additions=additions,
                        deletions=deletions,
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
                before = (
                    _backup_path(self._chat_id, backup.backup_name)
                    if backup.backup_name
                    else None
                )
                diff, additions, deletions = _diff_metadata(
                    before, live, _display_path(abs_path)
                )
                snapshot[abs_path] = FileBackup(
                    backup_name=backup.backup_name,
                    version=backup.version,
                    backup_time=backup.backup_time,
                    after_hash=_content_hash(live),
                    after_exists=True,
                    diff=diff,
                    additions=additions,
                    deletions=deletions,
                )

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
        conflicts: list[str] = []
        for abs_path, backup in snapshot.items():
            live = Path(abs_path)
            current_hash = _content_hash(live)
            base_path = (
                _backup_path(chat_id, backup.backup_name)
                if backup.backup_name
                else None
            )
            base_hash = _content_hash(base_path) if base_path else None
            current_is_after = (
                live.exists() == backup.after_exists
                and current_hash == backup.after_hash
            )
            current_is_base = (
                live.exists() == (backup.backup_name is not None)
                and current_hash == base_hash
            )
            if not current_is_after and not current_is_base:
                conflicts.append(abs_path)
        if conflicts:
            raise FileRestoreConflictError(conflicts)

        changed: list[str] = []
        for abs_path, backup in snapshot.items():
            try:
                live = Path(abs_path)
                if live.exists() == (backup.backup_name is not None) and (
                    _content_hash(live)
                    == (
                        _content_hash(_backup_path(chat_id, backup.backup_name))
                        if backup.backup_name
                        else None
                    )
                ):
                    continue

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
                "display_path": _display_path(path),
                "backup_name": b.backup_name,
                "version": b.version,
                "backup_time": b.backup_time.isoformat(),
                "after_hash": b.after_hash,
                "after_exists": b.after_exists,
                "diff": b.diff,
                "additions": b.additions,
                "deletions": b.deletions,
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
                after_hash=entry.get("after_hash"),
                after_exists=entry.get("after_exists", True),
                diff=entry.get("diff", ""),
                additions=entry.get("additions", 0),
                deletions=entry.get("deletions", 0),
            )
        return result
