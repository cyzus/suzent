"""Resuming a run after automatic tool approvals adds no user message.

pydantic-ai sends any prompt that is not None, so resuming with "" put an empty
user message into the model's context after every auto-approved tool call, and
the display log grew an empty user row for each one.
"""

from types import SimpleNamespace

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import DeferredToolRequests

import suzent.streaming as streaming
from suzent.core.agent_deps import AgentDeps
from suzent.core.chat_processor import _rebuild_display_messages
from suzent.permissions.models import CommandDecision


@pytest.fixture
def auto_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    async def allow(self, request, context):
        return SimpleNamespace(
            behavior=CommandDecision.ALLOW,
            reason="allowed",
            reason_code="test",
            metadata={},
            source=SimpleNamespace(value="test"),
        )

    async def no_audit(**kwargs) -> None:
        return None

    monkeypatch.setattr(streaming.PermissionEngine, "evaluate", allow)
    monkeypatch.setattr(
        streaming.PermissionContext,
        "from_deps",
        staticmethod(lambda deps: SimpleNamespace(mode=SimpleNamespace(value="auto"))),
    )
    monkeypatch.setattr(streaming, "record_permission_audit", no_audit)
    monkeypatch.setattr(
        streaming,
        "_permission_decision_payload",
        lambda **kwargs: {"toolCallId": kwargs["tool_call_id"]},
    )


async def test_an_auto_approved_tool_call_resumes_without_a_prompt(auto_allow) -> None:
    agent = Agent(TestModel(), output_type=[str, DeferredToolRequests])

    @agent.tool_plain(requires_approval=True)
    def ping() -> str:
        return "pong"

    deps = AgentDeps()
    async for _ in streaming.stream_agent_responses(agent, "hello", deps=deps):
        pass

    history = deps.last_messages or []
    prompts = [
        part.content
        for message in history
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    ]
    assert prompts == ["hello"]
    assert any(
        isinstance(part, ToolReturnPart)
        for message in history
        if isinstance(message, ModelRequest)
        for part in message.parts
    )


def test_old_empty_prompts_leave_no_empty_rows() -> None:
    history = [
        ModelRequest(parts=[UserPromptPart(content="hello")]),
        ModelResponse(parts=[]),
        ModelRequest(
            parts=[
                ToolReturnPart(tool_name="ping", content="pong", tool_call_id="c1"),
                UserPromptPart(content=""),
            ]
        ),
    ]

    rows = _rebuild_display_messages(history)

    assert [row for row in rows if row["role"] == "user"] == [
        {
            "role": "user",
            "content": "hello",
            "timestamp": rows[0]["timestamp"],
        }
    ]
