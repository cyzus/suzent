from types import SimpleNamespace

from suzent.prompts import (
    STATIC_INSTRUCTIONS,
    build_session_guidance_section,
    format_session_guidance_debug,
    register_dynamic_instructions,
)
from suzent.tools.registry import (
    get_tool_session_guidance,
    get_tool_session_guidance_entries,
)


class _FakeAgent:
    def __init__(self) -> None:
        self.functions = []

    def instructions(self, fn):
        self.functions.append(fn)
        return fn


def test_static_instructions_do_not_embed_date_context():
    assert "Today's date:" not in STATIC_INSTRUCTIONS


def test_register_dynamic_instructions_registers_all_sections():
    agent = _FakeAgent()
    register_dynamic_instructions(
        agent,
        base_instructions="",
        memory_context="",
    )

    assert len(agent.functions) == 8


def test_register_dynamic_instructions_environment_uses_host_paths():
    agent = _FakeAgent()
    register_dynamic_instructions(
        agent,
        base_instructions="",
        memory_context="",
    )

    funcs = {fn.__name__: fn for fn in agent.functions}
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            sandbox_enabled=False,
            workspace_root="D:/workspace/suzent",
            custom_volumes=[],
            skill_manager=None,
            social_context={},
        )
    )

    result = funcs["inject_environment_context"](ctx)

    assert "# Environment: Host" in result
    assert "Do NOT use virtual `/mnt/...` paths." in result


def test_register_dynamic_instructions_empty_social_returns_empty_string():
    agent = _FakeAgent()
    register_dynamic_instructions(
        agent,
        base_instructions="",
        memory_context="",
    )

    funcs = {fn.__name__: fn for fn in agent.functions}
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            sandbox_enabled=False,
            workspace_root="D:/workspace/suzent",
            custom_volumes=[],
            skill_manager=None,
            social_context={},
        )
    )

    assert funcs["inject_social_context"](ctx) == ""


def test_build_session_guidance_section_tool_aware_rules():
    entries = get_tool_session_guidance_entries(
        ["BashTool", "ReadFileTool", "SkillTool", "AskQuestionTool"]
    )
    assert [entry["tool_name"] for entry in entries] == [
        "BashTool",
        "ReadFileTool",
        "SkillTool",
        "AskQuestionTool",
    ]

    items = get_tool_session_guidance(
        ["BashTool", "ReadFileTool", "SkillTool", "AskQuestionTool"]
    )
    guidance = build_session_guidance_section(items)

    assert "# Session Guidance" in guidance
    assert "Reserve BashTool" in guidance
    assert "Read files with ReadFileTool" in guidance
    assert "use SkillTool early" in guidance
    assert "AskQuestionTool" in guidance


def test_format_session_guidance_debug_shows_order():
    text = format_session_guidance_debug(
        get_tool_session_guidance_entries(["SkillTool", "BashTool"])
    )

    assert text.startswith("[SessionGuidance] ordered tool guidance:")
    assert "1. priority=10 tool=BashTool" in text
    assert "2. priority=30 tool=SkillTool" in text
