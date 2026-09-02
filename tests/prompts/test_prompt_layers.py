"""Precedence between prompt sources is stated, and every section declares itself.

Assembly order is not precedence: a model does not reliably treat later text as
higher priority, so the ordering of `parts` cannot be relied on to resolve a
conflict between, say, retrieved memory and a permission rule. Precedence is
therefore told to the model in words, and enforced for real in the tool layer.

What is checked here is that the statement exists, that nothing below it claims
authority it should not have, and that a newly added dynamic section cannot skip
declaring which kind it is.
"""

from types import SimpleNamespace

from suzent.prompts import (
    DYNAMIC_SECTION_LAYERS,
    STATIC_INSTRUCTIONS,
    PromptLayer,
    register_dynamic_instructions,
)


class _FakeAgent:
    def __init__(self) -> None:
        self.functions: list = []

    def instructions(self, fn):
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
    assert "safety and permission rules first" in lowered


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


def test_no_lower_layer_section_claims_override_authority() -> None:
    """A section below SAFETY telling the model it overrides other instructions
    would contradict the precedence block."""
    agent = _FakeAgent()
    register_dynamic_instructions(agent, base_instructions="")
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            social_context={},
            permission_mode="default",
            permission_feedback=[],
            memory_manager=None,
            custom_volume_metadata={},
            sandbox_enabled=True,
            workspace_root="/w",
            suppress_environment_context=False,
            base_instructions="",
        )
    )
    for fn in agent.functions:
        layer = DYNAMIC_SECTION_LAYERS[fn.__name__]
        if layer <= PromptLayer.RUNTIME:
            continue
        try:
            text = fn(ctx)
        except Exception:
            continue
        if not isinstance(text, str):
            continue
        assert "override" not in text.lower(), fn.__name__
