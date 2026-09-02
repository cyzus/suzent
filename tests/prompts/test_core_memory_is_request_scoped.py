"""Core memory and the agent cache key must agree about what is per-request.

The agent instance is cached and reused. Anything scoped to a chat, a user or a
project is therefore only safe if it is either part of the cache key or resolved
fresh from `ctx.deps` on every run. These tests pin both halves of that bargain.
"""

from types import SimpleNamespace

import pytest

from suzent.agent_manager import _TRANSIENT_KEYS
from suzent.prompts import register_dynamic_instructions


def test_project_identity_stays_in_the_agent_cache_key():
    """RepoContext is built from static roots, so the project must key the cache."""
    for key in ("_project_context_dir", "_working_context_dir", "_repository_root"):
        assert key not in _TRANSIENT_KEYS, (
            f"{key} was excluded from the agent cache key; a cached agent would "
            "then carry one project's repository instructions into another"
        )


def test_chat_and_user_are_excluded_from_the_cache_key():
    """Excluded on purpose — scoped sections resolve per run from ctx.deps."""
    assert {"_chat_id", "_user_id"} <= _TRANSIENT_KEYS


# --- the injector itself ----------------------------------------------------


class _FakeAgent:
    def __init__(self):
        self.functions = []

    def instructions(self, fn):
        self.functions.append(fn)
        return fn


def _memory_injector(snapshot):
    agent = _FakeAgent()
    register_dynamic_instructions(agent, base_instructions="", memory_context=snapshot)
    fn = next(f for f in agent.functions if f.__name__ == "inject_memory_context")
    return fn


class _FakeManager:
    def __init__(self):
        self.seen = []

    async def get_core_memory_context(self, chat_id=None, user_id=None, **kwargs):
        self.seen.append((chat_id, user_id))
        return f"MEMORY[{user_id}/{chat_id}]"


@pytest.mark.asyncio
async def test_injector_reads_the_serving_chat_not_the_build_time_snapshot():
    manager = _FakeManager()
    fn = _memory_injector("STALE-SNAPSHOT")
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            memory_manager=manager,
            chat_id="chat-b",
            user_id="bob",
            sandbox_enabled=True,
            path_resolver=None,
        )
    )

    assert await fn(ctx) == "MEMORY[bob/chat-b]"
    assert manager.seen == [("chat-b", "bob")]


@pytest.mark.asyncio
async def test_injector_returns_nothing_when_memory_is_disabled():
    """deps.memory_manager is None exactly when memory is off."""
    fn = _memory_injector(None)
    ctx = SimpleNamespace(deps=SimpleNamespace(memory_manager=None))

    assert await fn(ctx) == ""


@pytest.mark.asyncio
async def test_injector_falls_back_to_the_snapshot_when_the_lookup_fails():
    class Broken:
        async def get_core_memory_context(self, **kwargs):
            raise RuntimeError("store offline")

    fn = _memory_injector("SNAPSHOT")
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            memory_manager=Broken(),
            chat_id="c",
            user_id="u",
            sandbox_enabled=True,
            path_resolver=None,
        )
    )

    assert await fn(ctx) == "SNAPSHOT"
