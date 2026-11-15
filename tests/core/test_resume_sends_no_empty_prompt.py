"""Resuming a run after automatic tool approvals adds no user message.

pydantic-ai sends any prompt that is not None, so resuming with "" put an empty
user message into the model's context after every auto-approved tool call, and
the display log grew an empty user row for each one.
"""

import json
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
from suzent.permissions.auto import AutoPermissionClassifier
from suzent.permissions.auto.models import AutoClassificationResult
from suzent.permissions.models import CommandDecision


def _patch_engine(monkeypatch: pytest.MonkeyPatch, behavior: CommandDecision) -> None:
    async def decide(self, request, context):
        return SimpleNamespace(
            behavior=behavior,
            reason="writes outside the workspace",
            reason_code="test",
            metadata={},
            source=SimpleNamespace(value="test"),
        )

    async def no_audit(**kwargs) -> None:
        return None

    monkeypatch.setattr(streaming.PermissionEngine, "evaluate", decide)
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


@pytest.fixture
def auto_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_engine(monkeypatch, CommandDecision.ALLOW)


@pytest.fixture
def auto_deny(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_engine(monkeypatch, CommandDecision.DENY)


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


async def test_a_policy_denial_tells_the_agent_why(auto_deny) -> None:
    agent = Agent(TestModel(), output_type=[str, DeferredToolRequests])

    @agent.tool_plain(requires_approval=True)
    def ping() -> str:
        return "pong"

    deps = AgentDeps()
    async for _ in streaming.stream_agent_responses(agent, "hello", deps=deps):
        pass

    returns = [
        part
        for message in deps.last_messages or []
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]
    assert returns
    assert "writes outside the workspace" in returns[0].model_response_str()


@pytest.mark.parametrize(
    ("profile", "high_risk", "behavior", "executed"),
    [
        ("headless", False, "allow", True),
        ("headless", True, "deny", False),
        ("interactive", True, "ask", False),
    ],
)
async def test_stream_applies_classifier_decision(
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    high_risk: bool,
    behavior: str,
    executed: bool,
) -> None:
    async def classify(self, **kwargs) -> AutoClassificationResult:
        return AutoClassificationResult(
            should_block=high_risk,
            reason="classifier verdict",
            confidence="high",
        )

    async def no_audit(**kwargs) -> None:
        return None

    monkeypatch.setattr(AutoPermissionClassifier, "classify", classify)
    monkeypatch.setattr(streaming, "record_permission_audit", no_audit)
    agent = Agent(TestModel(), output_type=[str, DeferredToolRequests])
    tool_runs = []

    @agent.tool_plain(requires_approval=True)
    def ping() -> str:
        tool_runs.append("ping")
        return "pong"

    events = []
    deps = AgentDeps(permission_mode="auto", interaction_profile=profile)
    async for chunk in streaming.stream_agent_responses(agent, "hello", deps=deps):
        if chunk.startswith("data: "):
            events.append(json.loads(chunk.removeprefix("data: ")))

    decisions = [
        event["value"]["behavior"]
        for event in events
        if event.get("name") == "tool_permission_decision"
    ]
    assert decisions == [behavior]
    assert bool(tool_runs) is executed
    assert deps.is_suspended is (behavior == "ask")
    assert any(event.get("name") == "tool_approval_request" for event in events) is (
        behavior == "ask"
    )
    assert not any(event["type"] == "RUN_ERROR" for event in events)


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
