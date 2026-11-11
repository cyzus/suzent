"""Tests for the one-shot `suzent run` command."""

import json
from contextlib import nullcontext
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from suzent.cli import app

runner = CliRunner()


def _sse(event: dict[str, Any]) -> bytes:
    return b"data: " + json.dumps(event).encode() + b"\n\n"


def _text(delta: str) -> bytes:
    return _sse({"type": "TEXT_MESSAGE_CONTENT", "delta": delta})


def _usage(**tokens: int) -> bytes:
    return _sse({"type": "CUSTOM", "name": "usage_update", "value": tokens})


def _approval(tool: str) -> bytes:
    return _sse(
        {
            "type": "CUSTOM",
            "name": "tool_approval_request",
            "value": {"approvalId": "a1", "toolCallId": "t1", "toolName": tool},
        }
    )


class FakeBackend:
    """A client whose `/chat` stream replays one scripted stream per request."""

    def __init__(self, *streams: list[bytes], models: list[str] | None = None):
        self.payloads: list[dict[str, Any]] = []
        self._streams = list(streams)
        self.client = MagicMock()
        self.client.config.get = AsyncMock(
            return_value={
                "models": models or ["openai/gpt-test"],
                "tools": ["ReadFileTool", "RunCommandTool", "WebSearchTool"],
            }
        )
        self.client.chat.create_chat = AsyncMock(return_value={"id": "chat-1"})
        self.client.chat.stream_message = self._stream

    async def _stream(self, payload: dict[str, Any], timeout: float | None = 60.0):
        self.payloads.append(payload)
        for chunk in self._streams.pop(0):
            yield chunk


@pytest.fixture
def invoke(tmp_path: Path):
    def _invoke(backend: FakeBackend, *args: str):
        with (
            patch("suzent.cli.run.get_client", return_value=backend.client),
            patch("suzent.cli.run._backend", return_value=nullcontext()),
        ):
            return runner.invoke(app, ["run", *args, "--cwd", str(tmp_path)])

    return _invoke


def test_run_prints_reply_and_exits(invoke, tmp_path: Path):
    backend = FakeBackend([_text("Hello "), _text("there")])

    result = invoke(backend, "Say hello")

    assert result.exit_code == 0
    assert "Hello there" in result.stdout
    config = backend.payloads[0]["config"]
    assert config["cwd"] == str(tmp_path.resolve())
    assert config["sandbox_enabled"] is False
    assert config["interaction_profile"] == "headless"
    assert config["auto_title"] is False
    assert backend.client.chat.create_chat.await_args.args[0]["config"] == config
    assert "permission_mode" not in config
    assert backend.payloads[0]["message"] == "Say hello"


def test_run_json_reports_usage_and_chat_id(invoke):
    backend = FakeBackend(
        [
            _text("done"),
            _usage(input_tokens=120, output_tokens=30, cache_read_tokens=80),
        ]
    )

    result = invoke(backend, "Do it", "--json", "--permission-mode", "full_access")

    assert result.exit_code == 0
    summary = json.loads(result.stdout)
    assert summary["result"] == "done"
    assert summary["chat_id"] == "chat-1"
    assert summary["is_error"] is False
    assert summary["usage"] == {
        "input_tokens": 120,
        "output_tokens": 30,
        "cache_read_tokens": 80,
    }
    assert backend.payloads[0]["config"]["permission_mode"] == "full_access"


def test_run_denies_approvals_instead_of_asking(invoke):
    backend = FakeBackend(
        [_approval("bash_execute"), _usage(input_tokens=10, output_tokens=1)],
        [_text("I could not run that."), _usage(input_tokens=15, output_tokens=5)],
    )

    result = invoke(backend, "Delete things", "--json")

    assert result.exit_code == 0
    assert backend.payloads[1]["resume_approvals"] == [
        {"request_id": "a1", "tool_call_id": "t1", "approved": False}
    ]
    summary = json.loads(result.stdout)
    assert summary["denied_tools"] == ["bash_execute"]
    assert summary["usage"] == {"input_tokens": 25, "output_tokens": 6}
    assert "full_access" in result.stderr


def test_run_fails_when_the_run_errors(invoke):
    backend = FakeBackend([_sse({"type": "RUN_ERROR", "message": "model exploded"})])

    result = invoke(backend, "Do it")

    assert result.exit_code == 1
    assert "model exploded" in result.stderr


def test_run_rejects_a_model_that_is_not_enabled(invoke):
    backend = FakeBackend([_text("never sent")])

    result = invoke(backend, "Do it", "--model", "openai/unknown")

    assert result.exit_code == 2
    assert "not enabled" in result.stderr
    assert backend.payloads == []


def test_run_mounts_cwd_when_the_sandbox_is_on(invoke, tmp_path: Path):
    backend = FakeBackend([_text("ok")])
    backend.client.config.get.return_value = {
        "models": ["openai/gpt-test"],
        "sandboxEnabled": True,
    }

    result = invoke(backend, "Do it")

    assert result.exit_code == 0
    config = backend.payloads[0]["config"]
    assert config["cwd"] == "/mnt/workspace"
    assert config["sandbox_enabled"] is True
    assert config["sandbox_volumes"] == [f"{tmp_path.resolve()}:/mnt/workspace"]


def test_run_reads_the_task_from_stdin(tmp_path: Path):
    backend = FakeBackend([_text("ok")])
    with (
        patch("suzent.cli.run.get_client", return_value=backend.client),
        patch("suzent.cli.run._backend", return_value=nullcontext()),
    ):
        result = runner.invoke(
            app, ["run", "--cwd", str(tmp_path)], input="Task from a pipe\n"
        )

    assert result.exit_code == 0
    assert backend.payloads[0]["message"] == "Task from a pipe"


def test_run_rejects_an_unknown_permission_mode(invoke):
    backend = FakeBackend([_text("never sent")])

    result = invoke(backend, "Do it", "--permission-mode", "yolo")

    assert result.exit_code == 2
    assert "full_access" in result.stderr
    assert backend.payloads == []


def test_run_limits_the_agent_to_the_named_tools(invoke):
    backend = FakeBackend([_text("ok")])

    result = invoke(backend, "Do it", "--tools", "ReadFileTool, RunCommandTool")

    assert result.exit_code == 0
    assert backend.payloads[0]["config"]["tools"] == ["ReadFileTool", "RunCommandTool"]


def test_run_rejects_an_unknown_tool(invoke):
    backend = FakeBackend([_text("never sent")])

    result = invoke(backend, "Do it", "--tools", "ReadFileTool,TeleportTool")

    assert result.exit_code == 2
    assert "TeleportTool" in result.stderr
    assert backend.payloads == []


@pytest.mark.parametrize(
    ("flags", "expected"),
    [(["--code-mode"], True), (["--no-code-mode"], False), ([], None)],
)
def test_run_sets_code_mode_only_when_asked(invoke, flags, expected):
    backend = FakeBackend([_text("ok")])

    result = invoke(backend, "Do it", *flags)

    assert result.exit_code == 0
    assert backend.payloads[0]["config"].get("code_mode") is expected


def test_run_follows_the_saved_sandbox_preference_over_the_default(invoke):
    backend = FakeBackend([_text("ok")])
    backend.client.config.get.return_value = {
        "models": ["openai/gpt-test"],
        "sandboxEnabled": False,
        "userPreferences": {"sandbox_enabled": True},
    }

    result = invoke(backend, "Do it")

    assert result.exit_code == 0
    config = backend.payloads[0]["config"]
    assert config["sandbox_enabled"] is True
    assert config["cwd"] == "/mnt/workspace"


def test_run_keeps_tool_arguments_out_of_stderr(invoke):
    call = {"toolCallId": "t1", "toolCallName": "run_command"}
    backend = FakeBackend(
        [
            _sse({"type": "TOOL_CALL_START", **call}),
            _sse(
                {
                    "type": "TOOL_CALL_ARGS",
                    "toolCallId": "t1",
                    "delta": '{"content": "curl -H \'Authorization: sk-secret\'"}',
                }
            ),
            _sse({"type": "TOOL_CALL_END", "toolCallId": "t1"}),
            _text("done"),
        ]
    )

    result = invoke(backend, "Do it")

    assert result.exit_code == 0
    assert "[tool] run_command" in result.stderr
    assert "sk-secret" not in result.output


def test_run_requires_a_task(invoke):
    result = invoke(FakeBackend(), "   ")

    assert result.exit_code == 2
