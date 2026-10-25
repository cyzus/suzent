"""A memory links back to the conversation it came from, and the page can say what
memory picked up this week."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from suzent.memory.markdown_store import MarkdownMemoryStore
from suzent.routes import memory_routes

LOG = """# Daily Log - 2026-10-20

## 09:15 — 3f2a9c1b
- [preference] Prefers neutral grey themes `kind:user source:user_said`

## 14:02 — 77aa0e11
- [technical] Run Python scripts with python -X utf8 `kind:experience source:outcome scope:windows-shell`
  > "UnicodeDecodeError"
"""


def _store(tmp_path) -> MarkdownMemoryStore:
    store = MarkdownMemoryStore(base_dir=tmp_path, notebook_dir=str(tmp_path / "nb"))
    store.archive_dir.mkdir(parents=True, exist_ok=True)
    (store.archive_dir / "2026-10-20.md").write_text(LOG, encoding="utf-8")
    return store


def test_a_fact_is_traced_to_the_heading_it_was_written_under(tmp_path):
    store = _store(tmp_path)

    assert store.find_fact_origin(
        "2026-10-20.md", "Run Python scripts with python -X utf8"
    ) == {"date": "2026-10-20", "time": "14:02", "chat_prefix": "77aa0e11"}
    assert store.find_fact_origin("2026-10-20.md", "never said") is None
    assert store.find_fact_origin("2026-01-01.md", "anything") is None


class _Store:
    def __init__(self, memory=None, rows=()):
        self.memory = memory
        self.rows = list(rows)

    async def get_memory(self, memory_id):
        return self.memory

    async def list_memories(self, **kwargs):
        return self.rows


async def test_origin_names_the_chat_when_its_prefix_is_unique(tmp_path, monkeypatch):
    memory = {
        "content": "Prefers neutral grey themes",
        "metadata": {"source_type": "archive_log", "source_file": "2026-10-20.md"},
    }
    manager = SimpleNamespace(store=_Store(memory), markdown_store=_store(tmp_path))
    monkeypatch.setattr(memory_routes, "get_memory_manager", lambda: manager)
    chat = SimpleNamespace(id="3f2a9c1b-full-id", title="Theme tweaks")
    db = SimpleNamespace(
        chat_log=SimpleNamespace(chat_ids=lambda: ["3f2a9c1b-full-id", "77aa0e11-x"]),
        get_chat=lambda chat_id: chat if chat_id == chat.id else None,
    )
    monkeypatch.setattr(memory_routes, "get_database", lambda: db)

    response = await memory_routes.get_archival_memory_origin(
        SimpleNamespace(path_params={"memory_id": "m1"})
    )

    assert json.loads(response.body) == {
        "date": "2026-10-20",
        "time": "09:15",
        "chat_id": "3f2a9c1b-full-id",
        "title": "Theme tweaks",
    }


async def test_a_vault_page_has_no_origin(monkeypatch):
    memory = {"content": "x", "metadata": {"source_type": "notebook"}}
    manager = SimpleNamespace(store=_Store(memory), markdown_store=None)
    monkeypatch.setattr(memory_routes, "get_memory_manager", lambda: manager)

    response = await memory_routes.get_archival_memory_origin(
        SimpleNamespace(path_params={"memory_id": "m1"})
    )

    assert response.status_code == 404


async def test_recent_changes_count_new_kinds_and_list_corrections(
    tmp_path, monkeypatch
):
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=30)

    def row(content, tags, created):
        meta = {"source_type": "archive_log", "tags": tags}
        kind = next((t[5:] for t in tags if t.startswith("kind:")), "untyped")
        return {
            "id": content,
            "content": content,
            "created_at": created,
            "metadata": meta | {"kind": kind},
        }

    rows = [
        row("Lives in Lisbon", ["kind:user", "revision"], now),
        row("Use -X utf8", ["kind:experience"], now),
        row("an early record", [], now),
        row("Lived in Berlin", ["kind:user"], old),
    ]
    store = _store(tmp_path)
    await store.append_confirmation(
        content="Prefers grey", matched="Prefers grey", date=now.strftime("%Y-%m-%d")
    )
    manager = SimpleNamespace(store=_Store(rows=rows), markdown_store=store)
    monkeypatch.setattr(memory_routes, "get_memory_manager", lambda: manager)

    response = await memory_routes.get_recent_memory_changes(
        SimpleNamespace(query_params={})
    )
    body = json.loads(response.body)

    assert body["added"] == {"user": 1, "experience": 1}
    assert body["revised"] == [{"id": "Lives in Lisbon", "content": "Lives in Lisbon"}]
    assert [c["content"] for c in body["confirmed"]] == ["Prefers grey"]
