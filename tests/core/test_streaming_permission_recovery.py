from types import SimpleNamespace

import pytest
from pydantic_ai.tools import ToolDenied

from suzent.streaming import (
    _deferred_approval_status,
    _DraftDisplayAccumulator,
    _tool_call_args_dict,
)


def test_deferred_tool_denied_is_not_treated_as_truthy_approval() -> None:
    assert _deferred_approval_status(ToolDenied()) == "denied"
    assert _deferred_approval_status(False) == "denied"
    assert _deferred_approval_status(True) == "executed"


def test_tool_call_args_dict_decodes_json_string_arguments() -> None:
    call = SimpleNamespace(
        args='{"content":"python --version","description":"Check Python version"}'
    )

    assert _tool_call_args_dict(call) == {
        "content": "python --version",
        "description": "Check Python version",
    }


def test_tool_call_args_dict_prefers_provider_decoder() -> None:
    call = SimpleNamespace(
        args="not-json",
        args_as_dict=lambda: {"content": "python --version"},
    )

    assert _tool_call_args_dict(call) == {"content": "python --version"}


@pytest.mark.parametrize(
    "event",
    [
        SimpleNamespace(
            type="TOOL_CALL_START", tool_call_id="call-1", tool_call_name="BashTool"
        ),
        SimpleNamespace(
            type="CUSTOM",
            name="tool_approval_request",
            value={
                "toolCallId": "call-1",
                "toolName": "BashTool",
                "approvalId": "approval-1",
            },
        ),
        SimpleNamespace(
            type="CUSTOM",
            name="tool_approval_result",
            value={
                "toolCallId": "call-1",
                "toolName": "BashTool",
                "status": "executed",
                "output": "ok",
            },
        ),
        SimpleNamespace(
            type="CUSTOM",
            name="tool_permission_resolution",
            value={"toolCallId": "call-1", "toolName": "BashTool", "behavior": "allow"},
        ),
    ],
)
def test_draft_recovers_tool_name_after_approval_resolution(
    event: SimpleNamespace,
) -> None:
    accumulator = _DraftDisplayAccumulator("chat-1", "run-1")
    accumulator.apply(
        SimpleNamespace(
            type="CUSTOM",
            name="tool_permission_resolution",
            value={"toolCallId": "call-1", "behavior": "allow"},
        )
    )
    accumulator.apply(event)
    assert len(accumulator.parts) == 1
    assert accumulator.parts[0]["toolName"] == "BashTool"
    assert accumulator.parts[0]["permissionResolution"]["behavior"] == "allow"


def test_draft_names_resolved_tool_without_an_earlier_start() -> None:
    accumulator = _DraftDisplayAccumulator("chat-1", "run-1")
    accumulator.apply(
        SimpleNamespace(
            type="CUSTOM",
            name="tool_permission_resolution",
            value={"toolCallId": "call-1", "toolName": "BashTool", "behavior": "allow"},
        )
    )
    assert accumulator.parts[0]["toolName"] == "BashTool"
    assert accumulator.parts[0]["state"] == "running"
