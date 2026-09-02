"""Precedence between prompt sources is stated, and every section declares itself.

Assembly order is not precedence: a model does not reliably treat later text as
higher priority, so the ordering of `parts` cannot be relied on to resolve a
conflict between, say, retrieved memory and a permission rule. Precedence is
therefore told to the model in words, and enforced for real in the tool layer.

What is checked here is that the statement exists, that nothing below it claims
authority it should not have, and that a newly added dynamic section cannot skip
declaring which kind it is.
"""

import inspect
import re
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from suzent.prompts import (
    DYNAMIC_SECTION_LAYERS,
    STATIC_INSTRUCTIONS,
    PromptLayer,
    register_dynamic_instructions,
)


class _FakeAgent:
    def __init__(self) -> None:
        self.functions: list[Callable[..., Any]] = []

    def instructions(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        self.functions.append(fn)
        return fn


def _registered_section_names() -> set[str]:
    agent = _FakeAgent()
    register_dynamic_instructions(agent, base_instructions="")
    return {fn.__name__ for fn in agent.functions}


def test_precedence_is_stated_to_the_model() -> None:
    assert "# Context Precedence" in STATIC_INSTRUCTIONS
    lowered = STATIC_INSTRUCTIONS.lower()
    assert "context, not authority" in lowered
    assert "safety and permission rules" in lowered
    assert "retrieved" in lowered


def test_the_statement_orders_preferences_above_retrieved_context() -> None:
    """PromptLayer puts USER_PREFERENCE above RETRIEVED_CONTEXT and the tests
    below require memory to be lowest, so the model-facing text — the only
    mechanism that actually resolves a conflict — must say the same."""
    lowered = STATIC_INSTRUCTIONS.lower()
    preferences = lowered.index("stored preferences")
    retrieved = lowered.index("retrieved")

    assert preferences < retrieved, "preferences must be stated as winning"


_AUTHORITY_CLAIMS = (
    re.compile(r"overrides?\s+(all|any|other|these|the\s+(above|system|user))"),
    re.compile(r"takes?\s+precedence"),
    re.compile(r"ignore\s+(all|any|other|the\s+(above|system))"),
)


def _claims_authority(text: str) -> str | None:
    """Match authority claims, not the word 'override'.

    A bare substring flags `model_override`, a parameter name in the models
    section, which claims nothing. Testing for the word rather than the meaning
    made this fail on legitimate text.
    """
    lowered = text.lower()
    for pattern in _AUTHORITY_CLAIMS:
        found = pattern.search(lowered)
        if found:
            return found.group(0)
    return None


def test_the_statement_names_the_prompt_injection_case() -> None:
    """The direction that matters: text asking to override a higher source."""
    assert "ignore a higher source" in STATIC_INSTRUCTIONS


def test_every_registered_section_declares_a_layer() -> None:
    """A new section must say what kind it is, so one that quietly claims
    authority is a visible choice rather than an oversight."""
    undeclared = _registered_section_names() - set(DYNAMIC_SECTION_LAYERS)

    assert not undeclared, f"add these to DYNAMIC_SECTION_LAYERS: {sorted(undeclared)}"


def test_the_layer_map_has_no_stale_entries() -> None:
    stale = set(DYNAMIC_SECTION_LAYERS) - _registered_section_names()

    assert not stale, f"no longer registered: {sorted(stale)}"


def test_permission_sections_are_safety_layer() -> None:
    for name in ("inject_permission_mode", "inject_permission_feedback"):
        assert DYNAMIC_SECTION_LAYERS[name] is PromptLayer.SAFETY


def test_memory_is_the_lowest_layer() -> None:
    """Retrieved context is the source most likely to carry someone else's
    instructions, so it must not outrank anything."""
    assert (
        DYNAMIC_SECTION_LAYERS["inject_memory_context"] is PromptLayer.RETRIEVED_CONTEXT
    )
    assert DYNAMIC_SECTION_LAYERS["inject_memory_context"] == max(
        DYNAMIC_SECTION_LAYERS.values()
    )


@pytest.mark.asyncio
async def test_no_lower_layer_section_claims_override_authority() -> None:
    """A section below SAFETY telling the model it overrides other instructions
    would contradict the precedence block.

    Async sections are awaited. An earlier version called them and type-checked
    the result, so `inject_memory_context` — the lowest layer, and the one most
    likely to carry someone else's instructions — returned a coroutine that was
    silently skipped. The test passed while checking nothing, and emitted only a
    RuntimeWarning to say so.
    """

    class _Memory:
        async def get_core_memory_context(self, **kwargs: Any) -> str:
            return "PERSONA: helpful. FACTS: none."

    agent = _FakeAgent()
    # Non-empty inputs throughout. With defaults, most sections return "" and a
    # scan over empty strings proves nothing — it would record a section as
    # checked while never seeing its body.
    register_dynamic_instructions(
        agent,
        base_instructions="Prefer terse answers.",
        session_guidance_items=["- Use ReadFileTool for files."],
        enabled_model_ids=["anthropic/claude-opus-4"],
        current_model_id="anthropic/claude-opus-4",
    )
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            chat_id="chat-1",
            user_id="user-1",
            social_context={"platform": "slack", "sender_name": "Ada"},
            permission_mode="plan",
            permission_feedback=["Do not push to main."],
            memory_manager=_Memory(),
            path_resolver=None,
            custom_volumes=["/host/data:/mnt/data"],
            custom_volume_metadata={"/mnt/data": {"description": "datasets"}},
            section_cache={},
            sandbox_enabled=True,
            workspace_root="/w",
            suppress_environment_context=False,
            base_instructions="Prefer terse answers.",
        )
    )

    checked = []
    for fn in agent.functions:
        # Skip SAFETY only. An earlier `<= RUNTIME` excluded every runtime
        # injector — environment, volumes, models, session guidance, social —
        # from a scan whose stated purpose is everything below safety.
        if DYNAMIC_SECTION_LAYERS[fn.__name__] is PromptLayer.SAFETY:
            continue
        text = fn(ctx)
        if inspect.isawaitable(text):
            text = await text
        assert isinstance(text, str), fn.__name__
        # Only count a section as inspected when it actually produced something.
        if not text.strip():
            continue
        checked.append(fn.__name__)
        claim = _claims_authority(text)
        assert claim is None, f"{fn.__name__} claims authority: {claim!r}"

    assert "inject_memory_context" in checked, (
        "the lowest-layer section must actually be examined, not skipped"
    )
    # Every non-safety section, and each one had to emit a body to count.
    expected = {
        name
        for name, layer in DYNAMIC_SECTION_LAYERS.items()
        if layer is not PromptLayer.SAFETY
    }
    missing = expected - set(checked)
    assert not missing, f"produced no text, so were never inspected: {sorted(missing)}"


# --- delegated agents get the same rules ------------------------------------


def test_the_precedence_block_is_shared_not_duplicated() -> None:
    """One source, so the two prompts cannot drift apart."""
    from suzent.prompts import CONTEXT_PRECEDENCE, SUBAGENT_PREAMBLE

    assert CONTEXT_PRECEDENCE in STATIC_INSTRUCTIONS
    assert CONTEXT_PRECEDENCE in SUBAGENT_PREAMBLE


def test_every_builtin_subagent_prompt_carries_precedence() -> None:
    """Sub-agents replace STATIC_INSTRUCTIONS wholesale instead of composing
    with it, so anything stated only there is missing from delegated work — and
    they still read repository files, which is where a conflicting instruction
    comes from."""
    import inspect

    from suzent.core import subagent_runner
    from suzent.prompts import SUBAGENT_INSTRUCTIONS

    source = inspect.getsource(subagent_runner)

    assert "SUBAGENT_PREAMBLE + SUBAGENT_INSTRUCTIONS" in source
    assert SUBAGENT_INSTRUCTIONS, "there should be profiles to cover"


def test_the_subagent_preamble_names_the_injection_case() -> None:
    from suzent.prompts import SUBAGENT_PREAMBLE

    assert "ignore a higher source" in SUBAGENT_PREAMBLE
    assert "context, not authority" in SUBAGENT_PREAMBLE.lower()


def test_a_custom_system_prompt_still_gets_precedence() -> None:
    """create_agent replaces STATIC_INSTRUCTIONS outright when a caller supplies
    static_instructions, so without prepending, a custom agent has nothing to
    resolve a conflict against — while still reading repository files."""
    import inspect

    from suzent import agent_manager

    source = inspect.getsource(agent_manager.create_agent)

    assert "CONTEXT_PRECEDENCE" in source
    assert 'config.get("static_instructions")' in source


def test_every_prompt_path_shares_one_precedence_source() -> None:
    """Four paths, not three: main agent, built-in sub-agent, caller-supplied
    prompt, and ACP sub-agents — whose instructions arrive as turn text and
    never touch subagent_prompt at all. I asserted "all three" one round before
    the fourth was found, so this counts the delegation branches explicitly."""
    import inspect

    from suzent import agent_manager
    from suzent.core import subagent_runner
    from suzent.prompts import CONTEXT_PRECEDENCE, SUBAGENT_PREAMBLE

    assert CONTEXT_PRECEDENCE in STATIC_INSTRUCTIONS
    assert CONTEXT_PRECEDENCE in SUBAGENT_PREAMBLE
    assert "CONTEXT_PRECEDENCE" in inspect.getsource(agent_manager.create_agent)

    runner = inspect.getsource(subagent_runner)
    assert "SUBAGENT_PREAMBLE + SUBAGENT_INSTRUCTIONS" in runner, "in-process branch"
    assert "system_preamble=SUBAGENT_PREAMBLE" in runner, "ACP branch"


def test_runtime_facts_are_ranked_above_project_files() -> None:
    """A repository file saying to use /mnt cannot make /mnt exist. Without a
    rank for observed facts, that conflict had no stated resolution."""
    lowered = STATIC_INSTRUCTIONS.lower()
    runtime = lowered.index("runtime facts")
    project = lowered.index("project files")

    assert runtime < project
    assert "cannot make a path exist" in lowered


def test_precedence_is_not_stated_twice_in_one_prompt() -> None:
    """Sub-agent prompts already carry it via SUBAGENT_PREAMBLE, and they reach
    create_agent as static_instructions. Prepending unconditionally stated the
    rules twice — wasted tokens, and it reads as though the copies might differ."""
    from suzent.agent_manager import create_agent  # noqa: F401
    from suzent.prompts import CONTEXT_PRECEDENCE, SUBAGENT_PREAMBLE

    import inspect

    from suzent import agent_manager

    source = inspect.getsource(agent_manager.create_agent)

    assert "CONTEXT_PRECEDENCE in _custom_instructions" in source
    # And the preamble really does contain it, so the guard fires.
    assert CONTEXT_PRECEDENCE in SUBAGENT_PREAMBLE


def test_the_acp_preamble_is_not_recorded_as_the_users_request() -> None:
    """It reaches the model but not the transcript. stream_acp_turn derives the
    persisted rows from `message`, so concatenating the preamble there showed
    internal policy text as though the user had typed it."""
    import inspect

    from suzent.acp import runtime
    from suzent.core import subagent_runner

    runner = inspect.getsource(subagent_runner)
    assert "system_preamble=SUBAGENT_PREAMBLE" in runner
    assert "{SUBAGENT_PREAMBLE}" not in runner.replace(
        "system_preamble=SUBAGENT_PREAMBLE", ""
    )

    acp = inspect.getsource(runtime.stream_acp_turn)
    # The transcript is derived before the preamble is attached.
    assert acp.index("persisted_content") < acp.index("system_preamble}")
