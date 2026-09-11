import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.responses import FileResponse

from suzent.database.models import ChatModel
from suzent.routes import sandbox_routes


@pytest.mark.parametrize("override_volumes", [None, [], ["/skills:/mnt/skills"]])
@pytest.mark.parametrize("legacy_cwd", [False, True])
async def test_preview_serves_image_in_chat_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    override_volumes: list[str] | None,
    legacy_cwd: bool,
) -> None:
    working_dir = tmp_path / "external-repository"
    working_dir.mkdir()
    image = working_dir / "photo.png"
    image.write_bytes(b"image content")
    chat = ChatModel(
        id="chat-1",
        working_directory=None if legacy_cwd else str(working_dir),
        config={
            "sandbox_enabled": True,
            "cwd": str(working_dir) if legacy_cwd else str(tmp_path / "stale-cwd"),
        },
    )
    monkeypatch.setattr(
        sandbox_routes,
        "get_database",
        lambda: SimpleNamespace(get_chat=lambda _: chat),
    )
    monkeypatch.setattr(sandbox_routes.CONFIG, "sandbox_enabled", False)
    monkeypatch.setattr(
        sandbox_routes.CONFIG, "sandbox_data_path", str(tmp_path / "sandbox")
    )
    monkeypatch.setattr(
        sandbox_routes, "get_effective_volumes", lambda volumes: volumes
    )
    monkeypatch.setattr(
        sandbox_routes,
        "_with_discovered_skill_volumes",
        lambda _chat_id, volumes, **_: volumes,
    )
    params = {"chat_id": chat.id, "path": str(image)}
    if override_volumes is not None:
        params["volumes"] = json.dumps(override_volumes)

    response = await sandbox_routes.serve_sandbox_file(
        SimpleNamespace(query_params=params)
    )

    assert isinstance(response, FileResponse)
    assert Path(response.path) == image
    resolver = sandbox_routes._get_resolver_for_request(chat.id, override_volumes)
    assert resolver.sandbox_enabled is True
    assert resolver.resolve("photo.png") == image
    assert not resolver.allows(tmp_path / "ungranted" / "photo.png")

    params["path"] = str(tmp_path / "ungranted" / "photo.png")
    denied = await sandbox_routes.serve_sandbox_file(
        SimpleNamespace(query_params=params)
    )
    assert denied.status_code in {403, 404}
