"""A denied tool is gone from the model, from execution and from ToolSearch.

Unchecking a tool only demotes it to the ToolSearch pool, and ``always_deny``
did nothing for an equipped tool that needs no approval, so there was no way to
say "this agent may not use this tool at all" (issue #253).
"""

from types import SimpleNamespace

from pydantic_ai import Agent, Tool
from pydantic_ai.capabilities import ToolSearch
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.native_tools._tool_search import TOOL_SEARCH_FUNCTION_TOOL_NAME

from suzent.tools.capability import ToolDenyCapability, is_denied


def _recording_model(seen: list[set[str]]) -> FunctionModel:
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append({tool.name for tool in info.function_tools})
        return ModelResponse(parts=[TextPart(content="done")])

    return FunctionModel(model)


def _agent(seen: list[set[str]], capability: ToolDenyCapability) -> Agent:
    def web_search() -> str:
        """Search the web."""
        return "results"

    def webpage_fetch() -> str:
        """Fetch a page."""
        return "page"

    def read_file() -> str:
        """Read a file."""
        return "contents"

    # A second deferred tool keeps ``search_tools`` offered once the first is denied.
    def page_notes() -> str:
        """Fetch saved notes about a page."""
        return "notes"

    return Agent(
        _recording_model(seen),
        deps_type=SimpleNamespace,
        tools=[
            web_search,
            read_file,
            Tool(webpage_fetch, defer_loading=True),
            Tool(page_notes, defer_loading=True),
        ],
        capabilities=[ToolSearch(), capability],
    )


def _deps(policy: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(tool_approval_policy=policy or {})


async def test_a_denied_equipped_tool_is_not_offered_to_the_model():
    seen: list[set[str]] = []
    agent = _agent(seen, ToolDenyCapability(frozenset({"WebSearchTool"})))

    await agent.run("go", deps=_deps())

    assert "web_search" not in seen[0]
    assert "read_file" in seen[0]


async def test_always_deny_now_covers_an_equipped_approval_free_tool():
    seen: list[set[str]] = []
    agent = _agent(seen, ToolDenyCapability())

    await agent.run("go", deps=_deps({"web_search": "always_deny"}))

    assert "web_search" not in seen[0]


def _searching_model(found: list[str]) -> FunctionModel:
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        returns = [
            part
            for message in messages
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ]
        if not returns:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name=TOOL_SEARCH_FUNCTION_TOOL_NAME,
                        args={"queries": ["fetch page"]},
                        tool_call_id="search-1",
                    )
                ]
            )
        found.append(str(returns[0].content))
        return ModelResponse(parts=[TextPart(content="done")])

    return FunctionModel(model)


async def _search_result(capability: ToolDenyCapability) -> str:
    found: list[str] = []
    agent = _agent([], capability)
    await agent.run("go", model=_searching_model(found), deps=_deps())
    return found[0]


async def test_a_denied_deferred_tool_leaves_the_search_corpus():
    result = await _search_result(ToolDenyCapability(frozenset({"WebpageTool"})))

    assert "page_notes" in result
    assert "webpage_fetch" not in result


async def test_a_deferred_tool_that_is_not_denied_stays_searchable():
    result = await _search_result(ToolDenyCapability())

    assert "webpage_fetch" in result


def test_every_spelling_of_a_tool_is_matched():
    assert is_denied("web_search", frozenset({"WebSearchTool"}), {})
    assert is_denied("web_search", frozenset({"web_search"}), {})
    assert is_denied("run_command", frozenset({"ShellTool"}), {})
    assert is_denied("run_command", frozenset(), {"RunCommandTool": "always_deny"})
    assert not is_denied("web_search", frozenset(), {"web_search": "always_allow"})


def test_an_mcp_tool_is_denied_by_its_own_name():
    assert is_denied("github_create_issue", frozenset({"github_create_issue"}), {})


def test_a_builtin_cannot_be_denied():
    assert not is_denied("read_file", frozenset({"ReadFileTool"}), {})
    assert not is_denied("read_file", frozenset(), {"read_file": "always_deny"})
