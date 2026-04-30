"""Custom volume metadata probing and persistence helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess
from typing import Any

from suzent.logger import get_logger
from suzent.tools.filesystem.path_resolver import PathResolver

logger = get_logger(__name__)

_GIT_PROBE_TIMEOUT_SECONDS = 1.0
_NON_CODE_MOUNT_KINDS = {
    "/mnt/notebook": "notebook",
    "/mnt/skills": "skills",
}


def _volume_kind(mount_point: str) -> str:
    if mount_point in _NON_CODE_MOUNT_KINDS:
        return _NON_CODE_MOUNT_KINDS[mount_point]
    if mount_point in ("/workspace", "/mnt/workspace"):
        return "workspace"
    return "generic"


def probe_volume_metadata(
    volume: str,
    *,
    git_timeout: float = _GIT_PROBE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Probe one custom volume without raising on filesystem/Git failures."""
    parsed = PathResolver.parse_volume_string(volume)
    if parsed:
        host_path, mount_point = parsed
        mount_point = mount_point.strip().replace("\\", "/")
    else:
        host_path = volume
        mount_point = ""

    kind = _volume_kind(mount_point)
    metadata: dict[str, Any] = {
        "volume": volume,
        "host_path": host_path,
        "mount_point": mount_point,
        "kind": kind,
        "exists": False,
        "is_git_repo": None,
        "git_root": None,
        "status": "unknown",
        "error": None,
        "checked_at": datetime.now(),
    }

    try:
        exists = Path(host_path).exists()
        metadata["exists"] = exists
    except Exception as exc:
        metadata["status"] = "error"
        metadata["error"] = f"path check failed: {exc}"
        return metadata

    if not metadata["exists"]:
        metadata["status"] = "missing"
        return metadata

    if kind in {"notebook", "skills"}:
        metadata["status"] = "ok"
        return metadata

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=host_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=git_timeout,
        )
    except subprocess.TimeoutExpired:
        metadata["status"] = "timeout"
        metadata["error"] = f"git probe timed out after {git_timeout:.1f}s"
        return metadata
    except Exception as exc:
        metadata["status"] = "error"
        metadata["error"] = f"git probe failed: {exc}"
        return metadata

    if result.returncode == 0:
        metadata["status"] = "ok"
        metadata["is_git_repo"] = True
        metadata["git_root"] = result.stdout.strip() or None
    else:
        metadata["status"] = "ok"
        metadata["is_git_repo"] = False

    return metadata


def refresh_volume_metadata(db: Any, volumes: list[str] | None) -> None:
    """Refresh cached volume metadata for a set of configured volumes."""
    if not volumes:
        return

    items = [probe_volume_metadata(volume) for volume in volumes]
    db.save_volume_metadata(items)
    logger.debug("Refreshed metadata for {} custom volume(s)", len(items))
