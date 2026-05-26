from types import SimpleNamespace

import pytest

from suzent.tools.base import ToolErrorCode, ToolResult
from suzent.tools.skill_tool import SkillTool
from suzent.tools.agent_tool import AgentTool


class _DummySkillManager:
    def __init__(self, content=None):
        self.content = content

    def get_skill_content(self, skill_name, sandbox_enabled):
        return self.content

    def get_skill_descriptions(self):
        return "skill-a, skill-b"


@pytest.mark.asyncio
async def test_spawn_subagent_returns_structured_background_result(monkeypatch):
    async def fake_spawn_subagent(**kwargs):
        return SimpleNamespace(
            task_id="sub_12345678",
            status="queued",
            result_summary=None,
            error=None,
            chat_id="subagent-sub_12345678",
            parent_chat_id=kwargs["parent_chat_id"],
            tools_allowed=["BashTool"],
        )

    monkeypatch.setattr(
        "suzent.core.subagent_runner._resolve_tool_names",
        lambda tools_allowed: (["BashTool"], []),
    )
    monkeypatch.setattr(
        "suzent.core.subagent_runner.spawn_subagent",
        fake_spawn_subagent,
    )

    tool = AgentTool()
    ctx = SimpleNamespace(deps=SimpleNamespace(chat_id="chat-1"))

    result = await tool.forward(
        ctx,
        description="Inspect the workspace",
        tools_allowed=["BashTool"],
    )

    assert result.success
    assert result.metadata["task_id"] == "sub_12345678"
    assert result.metadata["resolved_tools"] == ["BashTool"]


@pytest.mark.asyncio
async def test_spawn_subagent_rejects_unrecognized_tools(monkeypatch):
    monkeypatch.setattr(
        "suzent.core.subagent_runner._resolve_tool_names",
        lambda tools_allowed: ([], list(tools_allowed)),
    )
    monkeypatch.setattr(
        "suzent.tools.registry.list_available_tools",
        lambda: ["BashTool", "ProcessTool"],
    )

    tool = AgentTool()
    ctx = SimpleNamespace(deps=SimpleNamespace(chat_id="chat-1"))

    result = await tool.forward(
        ctx,
        description="Inspect the workspace",
        tools_allowed=["NopeTool"],
    )

    assert not result.success
    assert result.error_code == ToolErrorCode.INVALID_ARGUMENT
    assert result.metadata["unrecognized_tools"] == ["NopeTool"]


@pytest.mark.asyncio
async def test_spawn_subagent_rejects_disabled_model(monkeypatch):
    monkeypatch.setattr(
        "suzent.tools.agent_tool.get_enabled_models_from_db",
        lambda: ["openai/gpt-4.1", "gemini/gemini-2.5-pro"],
    )

    tool = AgentTool()
    ctx = SimpleNamespace(deps=SimpleNamespace(chat_id="chat-1"))

    result = await tool.forward(
        ctx,
        description="Give an independent opinion",
        tools_allowed=[],
        model_override="anthropic/claude-sonnet-4",
    )

    assert not result.success
    assert result.error_code == ToolErrorCode.INVALID_ARGUMENT
    assert result.metadata["model_override"] == "anthropic/claude-sonnet-4"
    assert result.metadata["enabled_models"] == [
        "openai/gpt-4.1",
        "gemini/gemini-2.5-pro",
    ]


@pytest.mark.asyncio
async def test_spawn_subagent_accepts_effective_fallback_model(monkeypatch):
    captured = {}

    async def fake_spawn_subagent(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            task_id="sub_12345678",
            status="queued",
            result_summary=None,
            error=None,
            chat_id="subagent-sub_12345678",
            parent_chat_id=kwargs["parent_chat_id"],
            tools_allowed=[],
        )

    monkeypatch.setattr(
        "suzent.tools.agent_tool.get_enabled_models_from_db",
        lambda: ["openai/gpt-4.1"],
    )
    monkeypatch.setattr(
        "suzent.core.subagent_runner._resolve_tool_names",
        lambda tools_allowed: ([], []),
    )
    monkeypatch.setattr(
        "suzent.core.subagent_runner.spawn_subagent",
        fake_spawn_subagent,
    )

    tool = AgentTool()
    ctx = SimpleNamespace(deps=SimpleNamespace(chat_id="chat-1"))

    result = await tool.forward(
        ctx,
        description="Give an independent opinion",
        tools_allowed=[],
        model_override="openai/gpt-4.1",
    )

    assert result.success
    assert captured["model_override"] == "openai/gpt-4.1"


def test_spawn_subagent_guidance_does_not_embed_model_workflow():
    assert "coun" + "cil" not in AgentTool.session_guidance.lower()
    assert "model_override" not in AgentTool.session_guidance


def test_skill_tool_returns_structured_result(monkeypatch):
    dummy_manager = _DummySkillManager(content="# skill content")
    monkeypatch.setattr("suzent.skills.get_skill_manager", lambda: dummy_manager)

    tool = SkillTool()
    ctx = SimpleNamespace(
        deps=SimpleNamespace(skill_manager=dummy_manager, sandbox_enabled=True)
    )

    result = tool.forward(ctx, skill_name="skill-a")

    assert result.success
    assert result.message == "# skill content"
    assert result.metadata["skill_name"] == "skill-a"


def test_tool_result_requires_error_code_for_failures():
    with pytest.raises(ValueError, match="error_code is required"):
        ToolResult(success=False, message="failed")
