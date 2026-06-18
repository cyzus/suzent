from types import SimpleNamespace

from pydantic_ai.tools import ToolDenied

from suzent.streaming import (
    _deferred_approval_status,
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
