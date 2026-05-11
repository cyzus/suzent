import json

from starlette.testclient import TestClient

from suzent.server import app

client = TestClient(app)


def test_file_mentions_search_descends_into_non_matching_directories(tmp_path):
    nested_dir = tmp_path / "src" / "core"
    nested_dir.mkdir(parents=True)
    target = nested_dir / "agent_notes.md"
    target.write_text("hello", encoding="utf-8")

    response = client.get(
        "/sandbox/mentions",
        params={
            "chat_id": "draft",
            "query": "agent",
            "volumes": json.dumps([f"{tmp_path}:/mnt/project"]),
        },
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert any(item["path"] == "/mnt/project/src/core/agent_notes.md" for item in items)
