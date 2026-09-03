"""What every turn pays for, whether or not it can use it.

The static core and the two catalogue sections are part of the cached prefix,
so their cost is small per turn — but two of the rules in them fire when they
should not, and two of the sections describe capabilities the run may not have.
"""

from suzent.prompts import (
    CITATION_RULES_SECTION,
    STATIC_INSTRUCTIONS,
    build_citation_section,
    build_enabled_models_section,
)

MODELS = ["openai/gpt-4.1-mini", "gemini/gemini-3.1-pro-preview"]


# --- P2-1: the todo trigger --------------------------------------------------


def test_a_short_multi_tool_turn_does_not_demand_a_todo():
    """ "Multiple steps or tools" fires on "read two files and summarise", so an
    ordinary question left a durable task behind for the user to tidy up."""
    section = STATIC_INSTRUCTIONS[
        STATIC_INSTRUCTIONS.index("# Task Management") :
    ].split("#", 2)[1]

    assert "Multiple steps or tools" not in section
    for signal in ("long", "cross-turn", "delegated", "independently verifiable"):
        assert signal in section, signal


# --- P2-2: the output rule ---------------------------------------------------


def test_the_terseness_rule_is_scoped_to_progress_updates():
    """It reads as a rule for every response, so explanations and final reports
    were being held to a format meant for status lines."""
    assert "Progress updates:" in STATIC_INSTRUCTIONS
    assert "Final answers:" in STATIC_INSTRUCTIONS
    assert "Focus text output ONLY on" not in STATIC_INSTRUCTIONS


# --- P2-3 / P2-4: why these two are still always-on --------------------------


def test_every_unequipped_deferrable_tool_stays_reachable():
    """The constraint that killed the obvious version of P2-3 and P2-4.

    get_deferred_tool_functions(exclude=enabled_tool_names) registers every
    deferrable tool that is *not* equipped, unconditionally. So "not in the
    equipped set" does not mean "cannot be used" — it means the opposite: the
    tool is in the search pool. Gating a prompt section on equipment removes it
    in exactly the runs where the tool can still appear.
    """
    from suzent.tools.registry import _all_tool_classes, get_deferred_tool_functions

    for name in ("WebSearchTool", "WebpageTool", "AgentTool"):
        cls = next(c for c in _all_tool_classes() if c.name == name)
        assert getattr(cls, "deferrable", True), f"{name} is no longer deferrable"

    reachable = {t.name for t in get_deferred_tool_functions(set())}
    assert reachable, "nothing deferrable at all — the premise has changed"


def test_citation_rules_are_unconditional():
    """A run that reaches WebSearchTool through tool search receives t0_src_N
    ids. If the rules were gated away it would answer from web sources having
    never been taught the marker syntax — web claims with no working
    citations."""
    assert build_citation_section(None) == CITATION_RULES_SECTION
    assert build_citation_section(object()) == CITATION_RULES_SECTION


def test_the_model_catalogue_is_unconditional():
    """AgentTool's model_override schema points at this section. Gating it on
    AgentTool being equipped would leave the schema referring to a section that
    is not in the prompt."""
    section = build_enabled_models_section(MODELS, "m")

    assert all(model in section for model in MODELS)
