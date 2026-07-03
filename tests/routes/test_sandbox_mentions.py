import json

from starlette.testclient import TestClient

from suzent.config import CONFIG
from suzent.server import app

client = TestClient(app)


def _search(tmp_path):
    return client.get(
        "/sandbox/mentions",
        params={
            "chat_id": "draft",
            "query": "agent",
            "volumes": json.dumps([f"{tmp_path}:/mnt/project"]),
        },
    )


def test_file_mentions_search_descends_into_non_matching_directories(
    tmp_path, monkeypatch
):
    nested_dir = tmp_path / "src" / "core"
    nested_dir.mkdir(parents=True)
    target = nested_dir / "agent_notes.md"
    target.write_text("hello", encoding="utf-8")

    # Sandbox mode: mentions resolve to the virtual mount path.
    monkeypatch.setattr(CONFIG, "sandbox_enabled", True)
    response = _search(tmp_path)
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(item["path"] == "/mnt/project/src/core/agent_notes.md" for item in items)


def test_file_mentions_use_host_path_in_host_mode(tmp_path, monkeypatch):
    nested_dir = tmp_path / "src" / "core"
    nested_dir.mkdir(parents=True)
    target = nested_dir / "agent_notes.md"
    target.write_text("hello", encoding="utf-8")

    # Host mode: the agent is instructed to use real host paths, so a mention's
    # `path` must be the host filesystem path (virtual path kept separately).
    monkeypatch.setattr(CONFIG, "sandbox_enabled", False)
    response = _search(tmp_path)
    assert response.status_code == 200
    items = response.json()["items"]

    expected_host = str(target).replace("\\", "/")
    match = next((i for i in items if i["name"] == "agent_notes.md"), None)
    assert match is not None
    assert match["path"] == expected_host
    assert match["virtual_path"] == "/mnt/project/src/core/agent_notes.md"
