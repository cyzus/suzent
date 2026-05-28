from pathlib import Path

import pytest

from suzent.sync.conflicts import SyncConflictResolver
from suzent.sync.models import SyncConflict


@pytest.mark.asyncio
async def test_conflict_preview_rejects_paths_outside_payload(tmp_path: Path):
    payload_dir = tmp_path / "payload"
    outside_dir = tmp_path / "outside"
    payload_dir.mkdir()
    outside_dir.mkdir()
    outside = outside_dir / "pwned.md"
    outside.write_text("outside", encoding="utf-8")
    inside = payload_dir / "memory" / "MEMORY.md"
    inside.parent.mkdir()
    inside.write_text("inside", encoding="utf-8")

    conflict = SyncConflict(
        conflicting_paths=[
            "memory/MEMORY.md",
            "../outside/pwned.md",
            str(outside),
        ]
    )

    result = await SyncConflictResolver().resolve_preview(conflict, payload_dir)

    assert result.changed_paths == ["memory/MEMORY.md"]
    assert result.chosen_merge == {"memory/MEMORY.md": "inside"}
    assert not (payload_dir.parent / "outside" / "_sync").exists()
    assert (payload_dir / "_sync" / "conflict-previews" / "memory" / "MEMORY.md").exists()
