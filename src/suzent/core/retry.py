"""
Retry checkpoint management.

Before each agent turn we snapshot:
  - agent_state (bytes) — message history before the user's message
  - chat.messages     — display messages before the user's message
  - the user message text + file metadata
  - /persistence session directory  (chat-private sandbox files)
  - all custom-volume host directories  (user-mounted project dirs, etc.)

Checkpoint layout on disk:
  sandbox/checkpoints/{chat_id}/
    session/            ← copy of sandbox/sessions/{chat_id}/
    volumes/0/          ← copy of first custom-volume host dir
    volumes/1/          ← copy of second custom-volume host dir
    volume_map.json     ← [{host_path, container_path}, ...]

Deliberately NOT snapshotted
-----------------------------
/mnt/skills   — read-only shared mount, never written by the agent.
/shared       — shared across ALL chats; restoring it for one chat would
                roll back state produced by other concurrent chats and
                would corrupt the memory system (which lives in
                /shared/memory/).  If the agent modifies files in /shared
                those changes are intentionally left in place after retry.

On retry we restore all of the above, then re-run process_turn()
with the original user message.
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

# Container paths that should never be snapshotted (read-only shared mounts).
_SKIP_CONTAINER_PATHS = {"/mnt/skills"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_dir(chat_id: str) -> Path:
    from suzent.config import CONFIG

    return Path(CONFIG.sandbox_data_path) / "sessions" / chat_id


def _checkpoint_dir(chat_id: str) -> Path:
    from suzent.config import CONFIG

    return Path(CONFIG.sandbox_data_path) / "checkpoints" / chat_id


def _parse_volumes(config_snapshot: dict) -> List[dict]:
    """
    Return a list of {host_path, container_path} dicts for all effective volumes
    that are worth snapshotting (skips read-only shared mounts).
    """
    from suzent.config import get_effective_volumes
    from suzent.tools.filesystem.path_resolver import PathResolver

    per_chat = config_snapshot.get("sandbox_volumes") or []
    effective = get_effective_volumes(per_chat)

    result = []
    for vol in effective:
        parsed = PathResolver.parse_volume_string(vol)
        if not parsed:
            continue
        host_path, container_path = parsed
        if container_path in _SKIP_CONTAINER_PATHS:
            continue
        result.append({"host_path": host_path, "container_path": container_path})
    return result


def _snapshot_dir(src: Path, dst: Path) -> bool:
    """Copy *src* to *dst*, removing *dst* first. Returns True on success."""
    try:
        if dst.exists():
            shutil.rmtree(dst)
        if src.exists():
            shutil.copytree(src, dst)
        return True
    except Exception as e:
        logger.warning(f"[retry] snapshot {src} → {dst} failed: {e}")
        return False


def _restore_dir(src: Path, dst: Path) -> bool:
    """Restore *dst* from snapshot *src*. Returns True on success."""
    if not src.exists():
        return False
    try:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
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
) -> None:
    """
    Persist a retry checkpoint for *chat_id*.

    Called at the very start of process_turn(), before any state is mutated.
    Replaces any previously stored checkpoint for this chat.
    """
    try:
        from suzent.database import RetryCheckpointModel, get_database
        from sqlmodel import Session

        ckpt_root = _checkpoint_dir(chat_id)
        ckpt_root.parent.mkdir(parents=True, exist_ok=True)

        # Remove previous checkpoint entirely before writing a new one.
        if ckpt_root.exists():
            shutil.rmtree(ckpt_root)
        ckpt_root.mkdir(parents=True, exist_ok=True)

        has_file_snapshot = False

        # 1. Snapshot /persistence session directory.
        session_dir = _session_dir(chat_id)
        if _snapshot_dir(session_dir, ckpt_root / "session"):
            has_file_snapshot = True

        # 2. Snapshot each custom-volume host directory.
        volumes = _parse_volumes(config_snapshot)
        snapshotted_volumes = []
        for idx, vol in enumerate(volumes):
            host_path = Path(vol["host_path"])
            vol_dst = ckpt_root / "volumes" / str(idx)
            if _snapshot_dir(host_path, vol_dst):
                snapshotted_volumes.append(vol)
                has_file_snapshot = True
            else:
                # Keep the entry so indices stay aligned; mark as failed.
                snapshotted_volumes.append({**vol, "snapshot_failed": True})

        if snapshotted_volumes:
            (ckpt_root / "volume_map.json").write_text(
                json.dumps(snapshotted_volumes, ensure_ascii=False), encoding="utf-8"
            )

        db = get_database()
        checkpoint = RetryCheckpointModel(
            chat_id=chat_id,
            agent_state_before=agent_state_before,
            messages_before=list(messages_before),
            user_message=user_message,
            user_files=list(user_files),
            config_snapshot=dict(config_snapshot),
            has_file_snapshot=has_file_snapshot,
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
            f"session={'yes' if session_dir.exists() else 'no'}, "
            f"volumes={len([v for v in snapshotted_volumes if not v.get('snapshot_failed')])}"
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

        if checkpoint.has_file_snapshot:
            ckpt_root = _checkpoint_dir(chat_id)

            # Restore /persistence session directory.
            _restore_dir(ckpt_root / "session", _session_dir(chat_id))

            # Restore custom-volume host directories.
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
                    logger.warning(f"[retry] Volume restore failed for {chat_id}: {e}")

        return {
            "user_message": checkpoint.user_message,
            "user_files": list(checkpoint.user_files),
            "config_snapshot": dict(checkpoint.config_snapshot),
        }

    except Exception as e:
        logger.error(f"[retry] apply_retry_checkpoint failed for {chat_id}: {e}")
        return None
