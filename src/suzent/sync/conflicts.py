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
        for rel in conflict.conflicting_paths:
            if _is_secret_path(rel):
                continue
            path = payload_dir / rel
            if path.exists() and path.is_file() and _is_text_path(path):
                text = path.read_text(encoding="utf-8")
                preview = payload_dir / "_sync" / "conflict-previews" / rel
                preview.parent.mkdir(parents=True, exist_ok=True)
                preview.write_text(text, encoding="utf-8")
                chosen[rel] = text
                changed.append(rel)

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
