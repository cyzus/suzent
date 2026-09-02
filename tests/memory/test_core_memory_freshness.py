"""Core memory must reflect the files as they are now, not as they were at agent build.

Agents are cached and reused across chats and users, so anything captured in a
closure at construction time outlives the request it was built for. Core memory
used to be captured exactly that way: editing persona.md or a project's
context.md had no effect until something unrelated forced the agent to rebuild.
"""

import pytest

from suzent.memory.manager import MemoryManager
from suzent.memory.markdown_store import MarkdownMemoryStore


@pytest.fixture
def store(tmp_path):
    return MarkdownMemoryStore(
        base_dir=tmp_path / "memory", notebook_dir=tmp_path / "notebook"
    )


@pytest.fixture
def manager(store):
    return MemoryManager(store=None, markdown_store=store)


# --- revision fingerprint ---------------------------------------------------


def test_revision_changes_when_a_block_file_changes(store):
    before = store.core_memory_revision()
    store._block_path("persona").parent.mkdir(parents=True, exist_ok=True)
    store._block_path("persona").write_text("I am new", encoding="utf-8")

    assert store.core_memory_revision() != before


def test_revision_is_stable_when_nothing_changes(store):
    assert store.core_memory_revision() == store.core_memory_revision()


def test_revision_survives_missing_files(store):
    """A fresh install has none of these files; that must not raise."""
    assert isinstance(store.core_memory_revision(), tuple)


# --- cached accessor --------------------------------------------------------


@pytest.mark.asyncio
async def test_core_memory_refreshes_after_a_file_edit(manager, store):
    persona = store._block_path("persona")
    persona.parent.mkdir(parents=True, exist_ok=True)
    persona.write_text("ORIGINAL-PERSONA", encoding="utf-8")

    first = await manager.get_core_memory_context(chat_id="c1", user_id="u1")
    assert "ORIGINAL-PERSONA" in first

    persona.write_text("EDITED-PERSONA", encoding="utf-8")
    second = await manager.get_core_memory_context(chat_id="c1", user_id="u1")

    assert "EDITED-PERSONA" in second
    assert "ORIGINAL-PERSONA" not in second


@pytest.mark.asyncio
async def test_unchanged_files_are_served_from_cache(manager, store, monkeypatch):
    persona = store._block_path("persona")
    persona.parent.mkdir(parents=True, exist_ok=True)
    persona.write_text("STABLE", encoding="utf-8")

    await manager.get_core_memory_context(chat_id="c1", user_id="u1")

    calls = []
    original = manager.format_core_memory_for_context

    async def counting(*args, **kwargs):
        calls.append(1)
        return await original(*args, **kwargs)

    monkeypatch.setattr(manager, "format_core_memory_for_context", counting)
    await manager.get_core_memory_context(chat_id="c1", user_id="u1")

    assert calls == [], "unchanged core memory should not be re-rendered"


@pytest.mark.asyncio
async def test_cache_is_scoped_per_chat(manager, store):
    """Two chats share persona/user/facts but not their project context."""
    persona = store._block_path("persona")
    persona.parent.mkdir(parents=True, exist_ok=True)
    persona.write_text("SHARED", encoding="utf-8")

    a = await manager.get_core_memory_context(chat_id="chat-a", user_id="u1")
    b = await manager.get_core_memory_context(chat_id="chat-b", user_id="u1")

    assert "SHARED" in a and "SHARED" in b


@pytest.mark.asyncio
async def test_legacy_path_without_markdown_store_is_not_cached():
    """No markdown store means no cheap revision, so every read must go live.

    This is also what keeps the legacy LanceDB path from serving one user's
    persona to another: nothing is retained between calls.
    """

    class FakeLanceStore:
        def __init__(self):
            self.calls = []

        async def get_all_memory_blocks(self, chat_id=None, user_id=None):
            self.calls.append(user_id)
            return {"persona": f"persona-for-{user_id}"}

    lance = FakeLanceStore()
    manager = MemoryManager(store=lance, markdown_store=None)

    first = await manager.get_core_memory_context(chat_id="c", user_id="alice")
    second = await manager.get_core_memory_context(chat_id="c", user_id="bob")

    assert "persona-for-alice" in first
    assert "persona-for-bob" in second
    assert lance.calls == ["alice", "bob"]


# --- Codex review follow-ups (PR #163) --------------------------------------


class _FakeResolver:
    """Minimal stand-in for PathResolver in host (non-sandbox) mode."""

    def __init__(self, tmp_path, working, notebook="/host/notebook"):
        self.sandbox_data_path = tmp_path
        self.custom_mounts = {"/mnt/notebook": notebook}
        self._working = working

    def get_working_dir(self):
        return self._working


@pytest.mark.asyncio
async def test_changing_the_working_dir_bypasses_the_cache(manager, store, tmp_path):
    """Host mode renders cwd into the prompt, so it is part of the cache identity."""
    persona = store._block_path("persona")
    persona.parent.mkdir(parents=True, exist_ok=True)
    persona.write_text("P", encoding="utf-8")

    first = await manager.get_core_memory_context(
        chat_id="c1",
        user_id="u1",
        sandbox_enabled=False,
        path_resolver=_FakeResolver(tmp_path, tmp_path / "project-a"),
    )
    second = await manager.get_core_memory_context(
        chat_id="c1",
        user_id="u1",
        sandbox_enabled=False,
        path_resolver=_FakeResolver(tmp_path, tmp_path / "project-b"),
    )

    assert "project-a" in first
    assert "project-b" in second, "stale cwd served from cache after the mount changed"


def test_resolver_paths_carry_the_notebook_mount(manager, tmp_path):
    """The mount does not change the rendered text today, but it is resolver
    state the section is built from, so it belongs in the cache identity rather
    than being rediscovered as a bug the day the template starts printing it."""
    a = manager._resolver_paths(
        False, _FakeResolver(tmp_path, tmp_path / "p", notebook="/mnt/first")
    )
    b = manager._resolver_paths(
        False, _FakeResolver(tmp_path, tmp_path / "p", notebook="/mnt/second")
    )

    assert a != b
    assert "/mnt/first" in a and "/mnt/second" in b


def test_resolver_paths_are_inert_in_sandbox_mode(manager, tmp_path):
    assert manager._resolver_paths(True, None) == (None, None, "/workspace/context.md")


@pytest.mark.asyncio
async def test_a_transient_failure_is_not_cached(manager, store, monkeypatch):
    """One bad read must not leave the chat without core memory indefinitely."""
    persona = store._block_path("persona")
    persona.parent.mkdir(parents=True, exist_ok=True)
    persona.write_text("RECOVERED", encoding="utf-8")

    async def boom(*args, **kwargs):
        raise OSError("transient")

    monkeypatch.setattr(manager, "get_core_memory", boom)
    assert await manager.get_core_memory_context(chat_id="c1", user_id="u1") == ""

    monkeypatch.undo()
    # Same revision as the failed attempt — recovery must not wait on a file edit.
    assert "RECOVERED" in await manager.get_core_memory_context(
        chat_id="c1", user_id="u1"
    )
