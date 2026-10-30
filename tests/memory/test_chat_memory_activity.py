"""The sidebar can say which memories a chat's latest turn used and what the chat saved."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from suzent.memory import lifecycle
from suzent.memory.markdown_store import MarkdownMemoryStore
from suzent.routes import memory_routes

CHAT = "3f2a9c1b-full-id"

OLD_LOG = """# Daily Log - 2026-10-19

## 22:40 — 3f2a9c1b
- [preference] Prefers dark editors `kind:user source:user_said`
"""

LOG = """# Daily Log - 2026-10-20

## 09:15 — 3f2a9c1b
- [preference] Prefers neutral grey themes `kind:user source:user_said`
- [technical] Runs `uv sync` before tests `kind:experience source:outcome`
  > "ModuleNotFoundError"

## 11:30 — 77aa0e11
- [goal] Wants a faster build `kind:user`

## 14:02 — 3f2a9c1b
- [preference] Prefers warm grey themes after all `kind:user revision`
"""


def _store(tmp_path) -> MarkdownMemoryStore:
    store = MarkdownMemoryStore(base_dir=tmp_path, notebook_dir=str(tmp_path / "nb"))
    store.archive_dir.mkdir(parents=True, exist_ok=True)
    (store.archive_dir / "2026-10-19.md").write_text(OLD_LOG, encoding="utf-8")
    (store.archive_dir / "2026-10-20.md").write_text(LOG, encoding="utf-8")
    return store


def test_chat_facts_come_from_its_own_headings_newest_first(tmp_path):
    facts = _store(tmp_path).find_chat_facts(
        CHAT, since="2026-10-20", include_legacy=True
    )

    assert [(f["time"], f["content"], f["kind"], f["revision"]) for f in facts] == [
        ("14:02", "Prefers warm grey themes after all", "user", True),
        ("09:15", "Runs `uv sync` before tests", "experience", False),
        ("09:15", "Prefers neutral grey themes", "user", False),
    ]


def test_chat_facts_reach_back_to_since_and_stop_at_limit(tmp_path):
    store = _store(tmp_path)

    assert len(store.find_chat_facts(CHAT, "2026-10-01", include_legacy=True)) == 4
    assert len(store.find_chat_facts(CHAT, "2026-10-01", 2, include_legacy=True)) == 2


async def test_new_logs_name_the_full_chat_so_shared_prefixes_stay_apart(tmp_path):
    store = MarkdownMemoryStore(base_dir=tmp_path, notebook_dir=str(tmp_path / "nb"))
    for chat_id, fact in [
        ("social-telegram-111", "Likes tea"),
        ("social-telegram-222", "Likes coffee"),
    ]:
        await store.append_daily_log(
            chat_id, [{"content": fact, "category": "preference"}], date="2026-10-20"
        )

    facts = store.find_chat_facts("social-telegram-111", since="2026-10-20")

    assert [f["content"] for f in facts] == ["Likes tea"]


def test_legacy_prefix_headings_count_only_when_the_caller_vouches(tmp_path):
    assert _store(tmp_path).find_chat_facts(CHAT, since="2026-10-01") == []


def test_recall_items_keep_what_the_sidebar_shows():
    items = lifecycle.recall_items(
        [
            {
                "id": 7,
                "content": "Prefers neutral grey themes",
                "metadata": {"category": "preference", "kind": "user", "x": 1},
            },
            {"id": "m2", "content": "No metadata", "metadata": "not-a-dict"},
        ]
    )

    assert items == [
        {
            "id": "7",
            "content": "Prefers neutral grey themes",
            "category": "preference",
            "kind": "user",
        },
        {"id": "m2", "content": "No metadata", "category": None, "kind": None},
    ]


async def test_rag_hook_records_the_turn_and_injects_the_same_memories(monkeypatch):
    saved = {}
    memories = [{"id": "m1", "content": "Likes rain", "metadata": {}}]

    class _Manager:
        async def find_relevant_memories(self, **kwargs):
            return memories

    db = SimpleNamespace(
        set_memory_recall=lambda chat_id, items: saved.update({chat_id: items})
    )
    monkeypatch.setattr("suzent.database.get_database", lambda: db)

    result = await lifecycle._memory_rag_hook(
        CHAT, SimpleNamespace(memory_manager=_Manager(), user_id="u"), "rain?"
    )

    assert "Likes rain" in result
    assert saved == {CHAT: [lifecycle.recall_items(memories)[0]]}


async def test_rag_hook_records_an_empty_turn(monkeypatch):
    saved = {}

    class _Manager:
        async def find_relevant_memories(self, **kwargs):
            return []

    db = SimpleNamespace(
        set_memory_recall=lambda chat_id, items: saved.update({chat_id: items})
    )
    monkeypatch.setattr("suzent.database.get_database", lambda: db)

    result = await lifecycle._memory_rag_hook(
        CHAT, SimpleNamespace(memory_manager=_Manager(), user_id="u"), "hi"
    )

    assert result is None
    assert saved == {CHAT: []}


async def test_activity_route_returns_recall_and_saved_facts(tmp_path, monkeypatch):
    chat = SimpleNamespace(id=CHAT, created_at=datetime(2026, 10, 20, 8, 0))
    recall = SimpleNamespace(
        items=[{"id": "m1", "content": "Likes rain"}],
        updated_at=datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc),
    )
    db = SimpleNamespace(
        get_chat=lambda chat_id: chat if chat_id == CHAT else None,
        get_memory_recall=lambda chat_id: recall,
        chat_log=SimpleNamespace(chat_ids=lambda: [CHAT, "77aa0e11-other"]),
    )
    monkeypatch.setattr(memory_routes, "get_database", lambda: db)
    manager = SimpleNamespace(markdown_store=_store(tmp_path))
    monkeypatch.setattr(memory_routes, "get_memory_manager", lambda: manager)

    response = await memory_routes.get_chat_memory_activity(
        SimpleNamespace(path_params={"chat_id": CHAT})
    )
    body = json.loads(response.body)

    assert body["recalled"] == {
        "items": [{"id": "m1", "content": "Likes rain"}],
        "updated_at": "2026-10-20T09:00:00+00:00",
    }
    # The 2026-10-19 fact predates the chat, so the prefix match is not trusted there.
    assert [f["date"] for f in body["saved"]] == ["2026-10-20"] * 3


async def test_activity_route_skips_legacy_prefixes_another_chat_shares(
    tmp_path, monkeypatch
):
    chat = SimpleNamespace(id=CHAT, created_at=datetime(2026, 10, 20, 8, 0))
    db = SimpleNamespace(
        get_chat=lambda chat_id: chat,
        get_memory_recall=lambda chat_id: None,
        chat_log=SimpleNamespace(chat_ids=lambda: [CHAT, "3f2a9c1b-another"]),
    )
    monkeypatch.setattr(memory_routes, "get_database", lambda: db)
    manager = SimpleNamespace(markdown_store=_store(tmp_path))
    monkeypatch.setattr(memory_routes, "get_memory_manager", lambda: manager)

    response = await memory_routes.get_chat_memory_activity(
        SimpleNamespace(path_params={"chat_id": CHAT})
    )

    assert json.loads(response.body)["saved"] == []


async def test_activity_route_without_memory_or_recall(monkeypatch):
    chat = SimpleNamespace(id=CHAT, created_at=datetime(2026, 10, 20, 8, 0))
    db = SimpleNamespace(
        get_chat=lambda chat_id: chat, get_memory_recall=lambda c: None
    )
    monkeypatch.setattr(memory_routes, "get_database", lambda: db)
    monkeypatch.setattr(memory_routes, "get_memory_manager", lambda: None)

    response = await memory_routes.get_chat_memory_activity(
        SimpleNamespace(path_params={"chat_id": CHAT})
    )

    assert json.loads(response.body) == {"recalled": None, "saved": []}


async def test_activity_route_404s_for_an_unknown_chat(monkeypatch):
    db = SimpleNamespace(get_chat=lambda chat_id: None)
    monkeypatch.setattr(memory_routes, "get_database", lambda: db)

    response = await memory_routes.get_chat_memory_activity(
        SimpleNamespace(path_params={"chat_id": "nope"})
    )

    assert response.status_code == 404
