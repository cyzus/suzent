"""Regression tests for archival-memory deletion route behavior."""

import json
from types import SimpleNamespace

import pytest

from suzent.routes import memory_routes


class _FakeIndexer:
    def __init__(self):
        self.calls = []

    async def reindex_file_now(self, **kwargs):
        self.calls.append(kwargs)
        return 1


class _FakeMarkdownStore:
    def __init__(self):
        self.tombstones = []

    async def append_tombstone(self, content: str) -> None:
        self.tombstones.append(content)


class _FakeStore:
    def __init__(self, memory):
        self.memory = memory
        self.deleted = []

    async def get_memory(self, memory_id: str):
        return self.memory

    async def delete_memory(self, memory_id: str) -> bool:
        self.deleted.append(memory_id)
        return True


class _FakeManager:
    def __init__(self, memory):
        self.store = _FakeStore(memory)
        self.markdown_store = _FakeMarkdownStore()
        self.embedding_gen = object()
        self._core_indexer = _FakeIndexer()


@pytest.mark.asyncio
async def test_delete_archive_memory_reindexes_for_memory_owner(monkeypatch):
    manager = _FakeManager(
        {
            "id": "mem-1",
            "content": "User likes compact dashboards.",
            "user_id": "other-user",
            "metadata": {
                "source_type": "archive_log",
                "source_file": "2026-06-11.md",
            },
        }
    )
    monkeypatch.setattr(memory_routes, "get_memory_manager", lambda: manager)

    request = SimpleNamespace(path_params={"memory_id": "mem-1"})
    response = await memory_routes.delete_archival_memory(request)
    body = json.loads(response.body)

    assert response.status_code == 200
    assert body == {"success": True}
    assert manager.markdown_store.tombstones == ["User likes compact dashboards."]
    assert manager.store.deleted == []
    assert manager._core_indexer.calls[0]["user_id"] == "other-user"


@pytest.mark.asyncio
async def test_delete_missing_memory_returns_404(monkeypatch):
    manager = _FakeManager(None)
    monkeypatch.setattr(memory_routes, "get_memory_manager", lambda: manager)

    request = SimpleNamespace(path_params={"memory_id": "missing"})
    response = await memory_routes.delete_archival_memory(request)
    body = json.loads(response.body)

    assert response.status_code == 404
    assert body == {"error": "Memory not found"}
