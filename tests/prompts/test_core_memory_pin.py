"""A core-memory edit mid-chat must not change the system prompt.

The system prompt sits in front of the whole conversation, so changing it makes
every provider re-read the cached history at full price. Edits reach the model
as a diff reminder on the next turn instead, which lands after the history.
"""

from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from suzent.memory.core_memory_pin import (
    MAX_DIFF_CHARS,
    core_memory_pins,
    core_memory_reminder_hook,
)
from suzent.prompts import register_dynamic_instructions


class _FakeAgent:
    def __init__(self):
        self.functions = []

    def instructions(self, fn):
        self.functions.append(fn)
        return fn


class _Memory:
    """Live core memory per user, editable between requests."""

    def __init__(self, **by_user: str):
        self.by_user = by_user

    async def get_core_memory_context(self, chat_id=None, user_id=None, **kwargs):
        return self.by_user[user_id]


def _injector():
    agent = _FakeAgent()
    register_dynamic_instructions(agent, base_instructions="")
    return next(f for f in agent.functions if f.__name__ == "inject_memory_context")


def _deps(memory, chat_id="chat-1", user_id="alice", **extra):
    return SimpleNamespace(
        memory_manager=memory,
        chat_id=chat_id,
        user_id=user_id,
        sandbox_enabled=True,
        path_resolver=None,
        **extra,
    )


FRESH = [ModelRequest(parts=[UserPromptPart(content="hi")])]
ONGOING = FRESH + [
    ModelResponse(parts=[TextPart(content="hello")]),
    ModelRequest(parts=[UserPromptPart(content="more")]),
]


@pytest.fixture(autouse=True)
def _clean_pins():
    core_memory_pins.clear()
    yield
    core_memory_pins.clear()


async def test_consecutive_requests_keep_the_system_prompt_after_an_edit():
    memory = _Memory(alice="persona: v1\nfacts: a")
    inject = _injector()
    deps = _deps(memory)

    first = await inject(SimpleNamespace(deps=deps, messages=FRESH))
    memory.by_user["alice"] = "persona: v1\nfacts: a, b"
    second = await inject(SimpleNamespace(deps=deps, messages=ONGOING))
    third = await inject(SimpleNamespace(deps=deps, messages=ONGOING))

    assert first == second == third == "persona: v1\nfacts: a"


async def test_the_edit_arrives_once_as_a_diff_reminder():
    memory = _Memory(alice="persona: v1\nfacts: a")
    inject = _injector()
    deps = _deps(memory)
    await inject(SimpleNamespace(deps=deps, messages=FRESH))

    memory.by_user["alice"] = "persona: v1\nfacts: a, b"
    reminder = await core_memory_reminder_hook("chat-1", deps)

    assert reminder is not None
    assert "-facts: a\n+facts: a, b" in reminder
    assert await core_memory_reminder_hook("chat-1", deps) is None


async def test_no_reminder_without_an_edit():
    memory = _Memory(alice="persona: v1")
    deps = _deps(memory)
    await _injector()(SimpleNamespace(deps=deps, messages=FRESH))

    assert await core_memory_reminder_hook("chat-1", deps) is None


async def test_a_new_conversation_follows_the_live_files():
    """No model response yet means nothing cached to protect."""
    memory = _Memory(alice="v1")
    inject = _injector()
    deps = _deps(memory)
    await inject(SimpleNamespace(deps=deps, messages=FRESH))

    memory.by_user["alice"] = "v2"
    assert await inject(SimpleNamespace(deps=deps, messages=FRESH)) == "v2"


async def test_pins_never_cross_users_sharing_a_chat_id():
    """The agent is shared across users; the pin must not be."""
    memory = _Memory(alice="ALICE", bob="BOB")
    inject = _injector()
    await inject(SimpleNamespace(deps=_deps(memory, user_id="alice"), messages=FRESH))

    served = await inject(
        SimpleNamespace(deps=_deps(memory, user_id="bob"), messages=ONGOING)
    )

    assert served == "BOB"


async def test_an_oversized_edit_repins_instead_of_sending_a_diff():
    memory = _Memory(alice="short")
    inject = _injector()
    deps = _deps(memory)
    await inject(SimpleNamespace(deps=deps, messages=FRESH))

    rewritten = "\n".join(f"line {i}" for i in range(MAX_DIFF_CHARS // 4))
    memory.by_user["alice"] = rewritten

    assert await core_memory_reminder_hook("chat-1", deps) is None
    assert await inject(SimpleNamespace(deps=deps, messages=ONGOING)) == rewritten


async def test_compaction_lets_the_pin_follow_the_live_files():
    memory = _Memory(alice="v1")
    inject = _injector()
    deps = _deps(memory)
    await inject(SimpleNamespace(deps=deps, messages=FRESH))
    memory.by_user["alice"] = "v2"

    core_memory_pins.forget("chat-1")

    assert await inject(SimpleNamespace(deps=deps, messages=ONGOING)) == "v2"
    assert await core_memory_reminder_hook("chat-1", deps) is None


async def test_stateless_runs_read_core_memory_live():
    """They get no reminders, so a pin would hide edits from them for good."""
    memory = _Memory(alice="v1")
    inject = _injector()
    deps = _deps(memory, stateless=True)
    await inject(SimpleNamespace(deps=deps, messages=FRESH))
    memory.by_user["alice"] = "v2"

    assert await inject(SimpleNamespace(deps=deps, messages=ONGOING)) == "v2"
    assert await core_memory_reminder_hook("chat-1", deps) is None
