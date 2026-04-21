"""
Retry checkpoint management.

Before each agent turn we snapshot:
  - agent_state (bytes) — message history before the user's message
  - chat.messages     — display messages before the user's message
  - the user message text + file metadata
  - per-file backups for every file touched during the turn (via FileTracker)

File-level snapshot strategy (mirrors Claude Code's fileHistory.ts)
-------------------------------------------------------------------
Instead of copytree-ing entire directories, we track only files that were
actually written by edit_file / write_file tools.  FileTracker.track_edit()
backs up each file *before* the first write; make_snapshot() returns a dict
mapping absolute path → FileBackup.  On retry we restore only those files.

Legacy directory snapshot (session dir + custom volumes) is kept as a
fallback for checkpoints that pre-date FileTracker, but is no longer
produced for new checkpoints.

Deliberately NOT snapshotted
-----------------------------
/mnt/skills   — read-only shared mount, never written by the agent.
/shared       — shared across ALL chats; restoring it for one chat would
                roll back state produced by other concurrent chats and
                would corrupt the memory system (which lives in
                /shared/memory/).  If the agent modifies files in /shared
                those changes are intentionally left in place after retry.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

# Container paths that should never be snapshotted (read-only shared mounts).
_SKIP_CONTAINER_PATHS = {"/mnt/skills"}


# ---------------------------------------------------------------------------
# Helpers (legacy directory snapshot — kept for apply fallback only)
# ---------------------------------------------------------------------------


def _session_dir(chat_id: str) -> Path:
    from suzent.config import CONFIG

    return Path(CONFIG.sandbox_data_path) / "sessions" / chat_id


def _checkpoint_dir(chat_id: str) -> Path:
    from suzent.config import CONFIG

    return Path(CONFIG.sandbox_data_path) / "checkpoints" / chat_id


def _rmtree_safe(path: Path) -> None:
    def _on_error(func, fpath, exc_info):
        logger.debug(f"[retry] rmtree skip {fpath}: {exc_info[1]}")

    shutil.rmtree(path, onerror=_on_error)


def _copy2_skip_errors(src, dst, **kwargs):
    try:
        shutil.copy2(src, dst, **kwargs)
    except OSError as e:
        logger.debug(f"[retry] copy skip {src}: {e}")


def _restore_dir(src: Path, dst: Path) -> bool:
    """Restore *dst* from snapshot *src*. Returns True on success."""
    if not src.exists():
        return False
    try:
        if dst.exists():
            _rmtree_safe(dst)
        shutil.copytree(
            src, dst, copy_function=_copy2_skip_errors, ignore_dangling_symlinks=True
        )
        return True
    except Exception as e:
        logger.warning(f"[retry] restore {src} → {dst} failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def save_retry_checkpoint(
    chat_id: str,
    agent_state_before: Optional[bytes],
    messages_before: list,
    user_message: str,
    user_files: list,
    config_snapshot: dict,
    file_snapshot: Optional[list] = None,
) -> None:
    """
    Persist a retry checkpoint for *chat_id*.

    ``file_snapshot`` is the serialised output of FileTracker.make_snapshot()
    (a list of dicts).  When provided, no directory copies are made.

    Called at the very start of process_turn(), before any state is mutated.
    Replaces any previously stored checkpoint for this chat.
    """
    try:
        from suzent.database import RetryCheckpointModel, get_database
        from sqlmodel import Session

        db = get_database()
        checkpoint = RetryCheckpointModel(
            chat_id=chat_id,
            agent_state_before=agent_state_before,
            messages_before=list(messages_before),
            user_message=user_message,
            user_files=list(user_files),
            config_snapshot=dict(config_snapshot),
            has_file_snapshot=bool(file_snapshot is not None),
            file_snapshot=file_snapshot or [],
            created_at=datetime.now(timezone.utc),
        )
        with Session(db.engine) as session:
            existing = session.get(RetryCheckpointModel, chat_id)
            if existing:
                session.delete(existing)
                session.flush()
            session.add(checkpoint)
            session.commit()

        logger.debug(
            f"[retry] checkpoint saved for {chat_id}: "
            f"file_snapshot_entries={len(file_snapshot) if file_snapshot else 0}"
        )

    except Exception as e:
        logger.error(f"[retry] save_retry_checkpoint failed for {chat_id}: {e}")


def load_retry_checkpoint(chat_id: str) -> Optional[Any]:
    """Return the stored RetryCheckpointModel for *chat_id*, or None."""
    try:
        from suzent.database import RetryCheckpointModel, get_database
        from sqlmodel import Session

        db = get_database()
        with Session(db.engine) as session:
            return session.get(RetryCheckpointModel, chat_id)
    except Exception as e:
        logger.error(f"[retry] load_retry_checkpoint failed for {chat_id}: {e}")
        return None


def apply_retry_checkpoint(chat_id: str) -> Optional[dict]:
    """
    Restore agent state, display messages, and files to the checkpoint state.

    Returns ``{"user_message": ..., "user_files": ..., "config_snapshot": ...}``
    so the caller can re-run process_turn() with the original inputs, or None
    if no checkpoint is found.
    """
    from suzent.database import ChatModel, get_database
    from sqlmodel import Session
    from sqlalchemy.orm.attributes import flag_modified

    checkpoint = load_retry_checkpoint(chat_id)
    if checkpoint is None:
        logger.warning(f"[retry] No checkpoint found for chat {chat_id}")
        return None

    try:
        db = get_database()

        # Restore agent state + display messages in DB.
        with Session(db.engine) as session:
            chat = session.get(ChatModel, chat_id)
            if chat:
                chat.agent_state = checkpoint.agent_state_before
                chat.messages = list(checkpoint.messages_before)
                flag_modified(chat, "messages")
                session.commit()

        # Restore files using the lightweight file-level snapshot when available.
        file_snapshot_data = getattr(checkpoint, "file_snapshot", None)
        if file_snapshot_data:
            try:
                from suzent.core.file_tracker import FileTracker

                snapshot = FileTracker.snapshot_from_json(file_snapshot_data)
                changed = FileTracker.apply_snapshot(chat_id, snapshot)
                logger.debug(
                    f"[retry] file snapshot applied for {chat_id}: {len(changed)} file(s) restored"
                )
            except Exception as e:
                logger.warning(f"[retry] file snapshot apply failed for {chat_id}: {e}")
        elif checkpoint.has_file_snapshot:
            # Legacy: restore from directory copies (pre-FileTracker checkpoints).
            ckpt_root = _checkpoint_dir(chat_id)
            _restore_dir(ckpt_root / "session", _session_dir(chat_id))

            vol_map_path = ckpt_root / "volume_map.json"
            if vol_map_path.exists():
                try:
                    volumes = json.loads(vol_map_path.read_text(encoding="utf-8"))
                    for idx, vol in enumerate(volumes):
                        if vol.get("snapshot_failed"):
                            continue
                        _restore_dir(
                            ckpt_root / "volumes" / str(idx),
                            Path(vol["host_path"]),
                        )
                except Exception as e:
                    logger.warning(
                        f"[retry] legacy volume restore failed for {chat_id}: {e}"
                    )

        return {
            "user_message": checkpoint.user_message,
            "user_files": list(checkpoint.user_files),
            "config_snapshot": dict(checkpoint.config_snapshot),
        }

    except Exception as e:
        logger.error(f"[retry] apply_retry_checkpoint failed for {chat_id}: {e}")
        return None
