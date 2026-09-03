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


# --- P2-3: citation rules ----------------------------------------------------


def test_citation_rules_are_dropped_when_nothing_can_be_cited():
    """1,681 characters of marker syntax for a format the run cannot produce."""
    assert build_citation_section({"ReadFileTool", "RunCommandTool"}) == ""


def test_citation_rules_survive_when_a_citing_tool_is_equipped():
    for tool in ("WebSearchTool", "WebpageTool"):
        assert build_citation_section({"ReadFileTool", tool}) == CITATION_RULES_SECTION


def test_the_rules_arrive_before_the_first_source_not_after():
    """Gated on equipment, never on whether a source exists yet: the model needs
    the marker syntax before the first tool call, so waiting for a source would
    teach it the format one turn too late."""
    assert build_citation_section({"WebSearchTool"}) == CITATION_RULES_SECTION


def test_an_unknown_equipment_set_keeps_the_rules():
    """A caller that does not say what is equipped is not evidence that nothing
    is. The safe direction here is to keep them."""
    assert build_citation_section(None) == CITATION_RULES_SECTION


# --- P2-4: the model catalogue -----------------------------------------------


def test_the_model_list_is_dropped_without_the_tool_that_uses_it():
    """model_override is an AgentTool argument. Beyond the tokens, the list sits
    in the cached prefix and changes whenever a model is toggled — so a chat
    that cannot spawn a sub-agent had its cache invalidated by an unrelated
    settings change."""
    assert build_enabled_models_section(MODELS, "m", {"ReadFileTool"}) == ""


def test_the_model_list_survives_with_agent_tool():
    section = build_enabled_models_section(MODELS, "m", {"AgentTool"})

    assert all(model in section for model in MODELS)


def test_an_unknown_equipment_set_keeps_the_model_list():
    section = build_enabled_models_section(MODELS, "m", None)

    assert all(model in section for model in MODELS)
