"""Each rule is stated in exactly one prompt layer.

The layers are assembled independently — static instructions, per-tool session
guidance, tool schemas, reminders — so the same rule drifting into two of them
is easy to do and invisible once done. It also costs twice: tokens on every
turn, and two places to update when the rule changes.

Ownership, per the audit:

* global safety and authorization  → STATIC_INSTRUCTIONS
* how to call a tool               → the tool's schema
* when to reach for a tool         → that tool's session_guidance
* what is available right now      → reminders
"""

from suzent.prompts import STATIC_INSTRUCTIONS
from suzent.skills.hooks import CATALOG_HEADER
from suzent.tools.agent_tool import AgentTool
from suzent.tools.shell.shell_tools import RunCommandTool
from suzent.tools.skill_tool import SkillTool


def _layers() -> dict[str, str]:
    return {
        "static": STATIC_INSTRUCTIONS,
        "shell_guidance": RunCommandTool.session_guidance or "",
        "agent_guidance": AgentTool.session_guidance or "",
        "skill_guidance": SkillTool.session_guidance or "",
        "skill_catalog_header": CATALOG_HEADER,
    }


def _layers_mentioning(*needles: str) -> set[str]:
    return {
        name
        for name, text in _layers().items()
        if any(needle.lower() in text.lower() for needle in needles)
    }


def test_shell_is_not_told_twice_to_leave_files_alone():
    """A tool-usage rule, so it belongs to the tool that would break it — and it
    should only be in the prompt when that tool is equipped."""
    assert _layers_mentioning("never use shell to read", "never** use bash") == {
        "shell_guidance"
    }


def test_the_verification_threshold_is_defined_once():
    """AgentTool provides the mechanism; the contract decides when it applies.
    Restating '3+ file edits' in both meant two places to change it."""
    assert _layers_mentioning("3+ file edits") == {"static"}


def test_when_to_use_a_skill_is_stated_once():
    """The catalog reminder fires only when the skill set changes, so a standing
    instruction placed there disappears after the first advertisement."""
    owners = _layers_mentioning(
        "skilltool", "matches a skill", "matches an available skill"
    )
    owners.discard("agent_guidance")  # unrelated: lists subagent profiles

    assert owners == {"skill_guidance", "skill_catalog_header"}
    assert "before starting" in SkillTool.session_guidance
    # The header names the resource; it does not instruct.
    assert "immediately" not in CATALOG_HEADER.lower()


def test_diagnose_before_retry_is_stated_once():
    """It was a Behavioral Guidelines bullet and step 1-2 of the Failure SOP."""
    assert STATIC_INSTRUCTIONS.lower().count("diagnose") == 1


def test_static_instructions_stay_within_budget():
    """A ceiling, so trimmed rules cannot quietly creep back. Raise it
    deliberately if the role genuinely grows."""
    assert len(STATIC_INSTRUCTIONS) < 3000, len(STATIC_INSTRUCTIONS)
