from __future__ import annotations

import asyncio
from pathlib import Path

from suzent.sync.models import ConflictResolutionResult, SyncConflict


class SyncConflictResolver:
    def __init__(self) -> None:
        self._cancel_event = asyncio.Event()

    def stop(self) -> None:
        self._cancel_event.set()

    def reset(self) -> None:
        self._cancel_event = asyncio.Event()

    async def resolve_preview(
        self, conflict: SyncConflict, payload_dir: Path
    ) -> ConflictResolutionResult:
        if self._cancel_event.is_set():
            return ConflictResolutionResult(status="cancelled")

        changed: list[str] = []
        chosen: dict[str, str] = {}
        payload_root = payload_dir.resolve()
        preview_root = payload_root / "_sync" / "conflict-previews"
        for rel in conflict.conflicting_paths:
            if _is_secret_path(rel):
                continue
            resolved = _resolve_payload_path(payload_root, rel)
            if resolved is None:
                continue
            safe_rel, path = resolved
            if path.exists() and path.is_file() and _is_text_path(path):
                text = path.read_text(encoding="utf-8")
                preview = (preview_root / safe_rel).resolve()
                preview.relative_to(preview_root)
                preview.parent.mkdir(parents=True, exist_ok=True)
                preview.write_text(text, encoding="utf-8")
                display_path = safe_rel.as_posix()
                chosen[display_path] = text
                changed.append(display_path)

        return ConflictResolutionResult(
            chosen_merge=chosen,
            explanation="Prepared text-file merge preview from portable sync payload.",
            changed_paths=changed,
            confidence=0.5,
            status="preview",
        )


def _is_secret_path(path: str) -> bool:
    lower = path.lower()
    return "secret" in lower or lower.endswith(".env") or "api_key" in lower


def _is_text_path(path: Path) -> bool:
    return path.suffix.lower() in {".md", ".json", ".yaml", ".yml", ".txt", ".toml"}


def _resolve_payload_path(payload_root: Path, rel: str) -> tuple[Path, Path] | None:
    raw = Path(rel)
    if raw.is_absolute():
        return None
    try:
        candidate = (payload_root / raw).resolve()
        safe_rel = candidate.relative_to(payload_root)
    except (OSError, ValueError):
        return None
    if not safe_rel.parts:
        return None
    return safe_rel, candidate
