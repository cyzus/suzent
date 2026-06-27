from types import SimpleNamespace

from suzent.prompts import (
    STATIC_INSTRUCTIONS,
    build_enabled_models_section,
    build_custom_volumes_section,
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

    assert len(agent.functions) == 11


def test_citation_rules_available_before_sources_exist():
    agent = _FakeAgent()
    register_dynamic_instructions(agent, base_instructions="", memory_context="")
    funcs = {fn.__name__: fn for fn in agent.functions}

    # The model needs the marker rules before it calls tools; labelled tool
    # output will provide the source ids later in the run.
    ctx = SimpleNamespace(deps=SimpleNamespace(citation_manager=None))
    result = funcs["inject_citation_rules"](ctx)
    assert "# Citation Rules" in result
    assert "citet0_src_1" in result


def test_citation_rules_appear_once_sources_exist():
    from suzent.core.citation_manager import CitationManager, CitationSourceType

    agent = _FakeAgent()
    register_dynamic_instructions(agent, base_instructions="", memory_context="")
    funcs = {fn.__name__: fn for fn in agent.functions}

    mgr = CitationManager()
    mgr.register(CitationSourceType.WEB_SEARCH, "Reuters", url="https://r.com")
    ctx = SimpleNamespace(deps=SimpleNamespace(citation_manager=mgr))

    result = funcs["inject_citation_rules"](ctx)
    # Rules show the marker syntax but NOT the source list — ids travel with
    # tool output, not the prompt.
    assert "# Citation Rules" in result
    assert "citet0_src_1" in result
    assert "Reuters" not in result
    assert "https://r.com" not in result


def test_citation_rules_are_static_and_cacheable():
    """Same string regardless of which sources are registered (no interpolation)."""
    from suzent.core.citation_manager import CitationManager, CitationSourceType

    agent = _FakeAgent()
    register_dynamic_instructions(agent, base_instructions="", memory_context="")
    inject = {fn.__name__: fn for fn in agent.functions}["inject_citation_rules"]

    mgr_a = CitationManager()
    mgr_a.register(CitationSourceType.WEB_SEARCH, "A", url="https://a.com")
    mgr_b = CitationManager()
    mgr_b.register(CitationSourceType.WEBPAGE, "B", url="https://b.com")

    out_a = inject(SimpleNamespace(deps=SimpleNamespace(citation_manager=mgr_a)))
    out_b = inject(SimpleNamespace(deps=SimpleNamespace(citation_manager=mgr_b)))
    assert out_a == out_b


def test_permission_feedback_instruction_includes_user_guidance():
    agent = _FakeAgent()
    register_dynamic_instructions(
        agent,
        base_instructions="",
        memory_context="",
    )
    funcs = {fn.__name__: fn for fn in agent.functions}
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            permission_feedback=["Use the staging environment instead"],
        )
    )

    result = funcs["inject_permission_feedback"](ctx)

    assert "# Permission Feedback" in result
    assert "Use the staging environment instead" in result


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


def test_register_dynamic_instructions_stateless_keeps_environment_context():
    agent = _FakeAgent()
    register_dynamic_instructions(
        agent,
        base_instructions="",
        memory_context="",
    )

    funcs = {fn.__name__: fn for fn in agent.functions}
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            stateless=True,
            suppress_environment_context=False,
            sandbox_enabled=False,
            workspace_root="D:/workspace/suzent",
            custom_volumes=[],
            skill_manager=None,
            social_context={},
        )
    )

    result = funcs["inject_environment_context"](ctx)

    assert "# Environment: Host" in result
    assert "D:/workspace/suzent" in result


def test_register_dynamic_instructions_can_suppress_environment_context():
    agent = _FakeAgent()
    register_dynamic_instructions(
        agent,
        base_instructions="",
        memory_context="",
    )

    funcs = {fn.__name__: fn for fn in agent.functions}
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            stateless=True,
            suppress_environment_context=True,
            sandbox_enabled=False,
            workspace_root="D:/workspace/suzent",
            custom_volumes=[],
            skill_manager=None,
            social_context={},
        )
    )

    assert funcs["inject_environment_context"](ctx) == ""


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


def test_notebook_volume_does_not_run_git_probe(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("notebook volumes should not be Git-probed")

    import subprocess

    monkeypatch.setattr(subprocess, "run", fake_run)

    deps = SimpleNamespace(custom_volumes=["C:/Users/example/Notebook:/mnt/notebook"])

    section = build_custom_volumes_section(deps)

    assert "(Notebook vault mount)" in section
    assert calls == []


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
    assert "BashTool is for shell/system commands ONLY" in guidance
    assert "Read files with ReadFileTool" in guidance or "read_file" in guidance.lower()
    assert "use SkillTool early" in guidance
    assert "AskQuestionTool" in guidance


def test_build_enabled_models_section_lists_current_and_available_models():
    section = build_enabled_models_section(
        ["openai/gpt-4.1", "gemini/gemini-2.5-pro"],
        current_model_id="openai/gpt-4.1",
    )

    assert "# Models" in section
    assert "Current model: `openai/gpt-4.1`" in section
    assert "Available models" in section
    assert "`openai/gpt-4.1`" in section
    assert "`gemini/gemini-2.5-pro`" in section


def test_format_session_guidance_debug_shows_order():
    text = format_session_guidance_debug(
        get_tool_session_guidance_entries(["SkillTool", "BashTool"])
    )

    assert text.startswith("[SessionGuidance] ordered tool guidance:")
    assert "1. priority=10 tool=BashTool" in text
    assert "2. priority=30 tool=SkillTool" in text
