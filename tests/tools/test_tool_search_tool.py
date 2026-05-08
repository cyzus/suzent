from types import SimpleNamespace

import pytest

from suzent.agent_manager import clear_unlocked_tools, get_unlocked_tools
from suzent.tools import tool_search_tool


@pytest.fixture(autouse=True)
def isolated_tool_catalog(monkeypatch):
    monkeypatch.setattr(
        tool_search_tool,
        "TOOL_CATALOG",
        {
            "WebpageTool": "Fetch and read a webpage.",
            "ImageGenerationTool": "Generate an image from a prompt.",
            "BashTool": "Execute shell commands.",
        },
    )
    monkeypatch.setattr(
        tool_search_tool,
        "TOOL_RUNTIME_NAMES",
        {
            "WebpageTool": "webpage_fetch",
            "ImageGenerationTool": "generate_image",
            "BashTool": "bash_execute",
        },
    )
    clear_unlocked_tools("test-chat")
    yield
    clear_unlocked_tools("test-chat")


@pytest.fixture
def no_stream_event(monkeypatch):
    async def _noop(chat_id: str, tool_names: list[str]) -> None:
        return None

    monkeypatch.setattr(tool_search_tool, "_emit_tool_activated", _noop)


def _ctx(*, base_tool_names=None, policy=None):
    return SimpleNamespace(
        deps=SimpleNamespace(
            chat_id="test-chat",
            base_tool_names=frozenset(base_tool_names or []),
            tool_approval_policy=policy or {},
        )
    )


@pytest.mark.asyncio
async def test_tool_search_does_not_guess_from_descriptions(no_stream_event):
    result = await tool_search_tool.tool_search(_ctx(), query="open a web page")

    assert "No tools matched" in result
    assert get_unlocked_tools("test-chat") == set()


@pytest.mark.asyncio
async def test_tool_search_matches_exact_class_key(no_stream_event):
    result = await tool_search_tool.tool_search(_ctx(), query="WebpageTool")

    assert result == (
        "Activated: WebpageTool. These tools are now available in your next step."
    )
    assert get_unlocked_tools("test-chat") == {"WebpageTool"}


@pytest.mark.asyncio
async def test_tool_search_matches_exact_runtime_key(no_stream_event):
    result = await tool_search_tool.tool_search(_ctx(), query="webpage_fetch")

    assert result == (
        "Activated: WebpageTool. These tools are now available in your next step."
    )
    assert get_unlocked_tools("test-chat") == {"WebpageTool"}


@pytest.mark.asyncio
async def test_tool_search_skips_denied_class_name(no_stream_event):
    result = await tool_search_tool.tool_search(
        _ctx(policy={"BashTool": "always_deny"}),
        query="BashTool",
    )

    assert "No tools matched" in result
    assert get_unlocked_tools("test-chat") == set()


@pytest.mark.asyncio
async def test_tool_search_skips_denied_runtime_name(no_stream_event):
    result = await tool_search_tool.tool_search(
        _ctx(policy={"generate_image": "always_deny"}),
        query="generate_image",
    )

    assert "No tools matched" in result
    assert get_unlocked_tools("test-chat") == set()


@pytest.mark.asyncio
async def test_tool_search_status_lists_available_and_active(no_stream_event):
    await tool_search_tool.tool_search(_ctx(), query="WebpageTool")

    result = await tool_search_tool.tool_search(
        _ctx(base_tool_names={"BashTool"}),
        query=None,
    )

    assert "ENABLED (user-selected): BashTool" in result
    assert "ACTIVE (AI-activated this session): WebpageTool" in result
    assert (
        "ImageGenerationTool (generate_image): Generate an image from a prompt."
        in result
    )
