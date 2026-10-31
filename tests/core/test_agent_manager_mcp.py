import asyncio
from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.toolsets import (
    ApprovalRequiredToolset,
    FunctionToolset,
    PrefixedToolset,
    SetMetadataToolset,
)

from suzent.agent_manager import _build_mcp_servers, _mcp_call_needs_approval
from suzent.permissions.context import PermissionContext
from suzent.permissions.engine import PermissionEngine, ToolPermissionRequest
from suzent.permissions.models import CommandDecision, PermissionMode


def test_builds_prefixed_v2_mcp_toolsets() -> None:
    config = {
        "mcp_urls": {"remote": "https://example.com/mcp"},
        "mcp_stdio_params": {
            "local": {
                "command": "python",
                "args": ["-m", "example_server"],
                "env": {"EXAMPLE": "1"},
            }
        },
        "mcp_enabled": {"remote": True, "local": True},
        "mcp_headers": {"remote": {"Authorization": "Bearer test"}},
    }

    toolsets = _build_mcp_servers(config)

    assert len(toolsets) == 2
    assert all(isinstance(toolset, ApprovalRequiredToolset) for toolset in toolsets)
    assert all(
        toolset.approval_required_func is _mcp_call_needs_approval
        for toolset in toolsets
    )
    with_metadata = [toolset.wrapped for toolset in toolsets]
    assert all(isinstance(toolset, SetMetadataToolset) for toolset in with_metadata)
    prefixed = [toolset.wrapped for toolset in with_metadata]
    assert all(isinstance(toolset, PrefixedToolset) for toolset in prefixed)
    assert [toolset.prefix for toolset in prefixed] == ["remote", "local"]
    assert all(isinstance(toolset.wrapped, MCPToolset) for toolset in prefixed)
    assert [toolset.wrapped.id for toolset in prefixed] == ["remote", "local"]


class _ToolDef:
    def __init__(self, metadata):
        self.metadata = metadata


@pytest.mark.parametrize(
    ("metadata", "needs_approval"),
    [
        ({"annotations": {"readOnlyHint": True}}, False),
        ({"annotations": {"readOnlyHint": False}}, True),
        ({"annotations": {"destructiveHint": False}}, True),
        ({"annotations": None}, True),
        (None, True),
    ],
)
def test_only_read_only_mcp_tools_skip_approval(metadata, needs_approval) -> None:
    assert _mcp_call_needs_approval(None, _ToolDef(metadata), {}) is needs_approval


def _server_like(read_only: bool):
    """A toolset wrapped exactly as _build_mcp_servers wraps an MCP server."""
    calls = []
    tools = FunctionToolset(
        metadata={"annotations": {"readOnlyHint": read_only}},
    )

    @tools.tool_plain
    def create_page(title: str) -> str:
        calls.append(title)
        return "created"

    toolset = (
        tools.prefixed("notion")
        .with_metadata(suzent_context_source="mcp")
        .approval_required(_mcp_call_needs_approval)
    )
    return toolset, calls


def test_writing_mcp_call_pauses_for_approval() -> None:
    toolset, calls = _server_like(read_only=False)
    agent = Agent(
        TestModel(), toolsets=[toolset], output_type=[str, DeferredToolRequests]
    )

    result = asyncio.run(agent.run("make a page"))

    assert isinstance(result.output, DeferredToolRequests)
    assert [call.tool_name for call in result.output.approvals] == [
        "notion_create_page"
    ]
    assert calls == []


def test_read_only_mcp_call_runs_without_approval() -> None:
    toolset, calls = _server_like(read_only=True)
    agent = Agent(
        TestModel(), toolsets=[toolset], output_type=[str, DeferredToolRequests]
    )

    result = asyncio.run(agent.run("make a page"))

    assert isinstance(result.output, str)
    assert len(calls) == 1


class _Resolver:
    def __init__(self, workspace: Path):
        self.workspace = workspace

    def resolve(self, value: str) -> Path:
        return self.workspace / value

    def get_working_dir(self) -> Path:
        return self.workspace

    def get_base_dir(self) -> Path:
        return self.workspace


@pytest.mark.parametrize(
    ("mode", "policy", "expected"),
    [
        (PermissionMode.DEFAULT, {}, CommandDecision.ASK),
        (
            PermissionMode.DEFAULT,
            {"notion_create_page": "always_allow"},
            CommandDecision.ALLOW,
        ),
        (
            PermissionMode.DEFAULT,
            {"notion_create_page": "always_deny"},
            CommandDecision.DENY,
        ),
        (PermissionMode.FULL_ACCESS, {}, CommandDecision.ALLOW),
        (PermissionMode.STRICT_READONLY, {}, CommandDecision.DENY),
        (PermissionMode.PLAN, {}, CommandDecision.DENY),
    ],
)
def test_deferred_mcp_call_follows_the_permission_mode(
    tmp_path, mode, policy, expected
) -> None:
    context = PermissionContext(
        chat_id="chat-1",
        mode=mode,
        interaction_profile="interactive",
        tool_approval_policy=policy,
        tool_permission_policies={},
        permission_rules=[],
        path_resolver=_Resolver(tmp_path),
        sandbox_enabled=False,
        transcript=[],
    )
    request = ToolPermissionRequest(
        tool_name="notion_create_page", args={"title": "x"}, tool_call_id="t1"
    )

    decision = asyncio.run(PermissionEngine().evaluate(request, context))

    assert decision.behavior == expected
