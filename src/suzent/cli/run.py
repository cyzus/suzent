"""One-shot, non-interactive agent run: ``suzent run "prompt"``.

Sends a single prompt, streams the reply, and exits. Unlike ``suzent agent
chat`` it never opens a REPL and never asks a question, so it suits scripts,
CI and benchmark harnesses. It starts a throwaway backend when none is running.
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import typer

from suzent.client import get_client
from suzent.client.base import ClientError, _is_loopback_url, get_server_url
from suzent.core.stream_parser import (
    ApprovalRequest,
    ErrorEvent,
    StreamParser,
    TextChunk,
    ToolCall,
    UsageUpdate,
)

EXIT_RUN_FAILED = 1
EXIT_USAGE = 2

_SUMMED_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "requests",
)


@dataclass
class RunResult:
    """What one headless run produced."""

    chat_id: str
    text: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    denied_tools: list[str] = field(default_factory=list)
    error: str | None = None

    def add_usage(self, usage: dict[str, Any]) -> None:
        """Add one stream's usage; a turn resumed after a denial reports again."""
        for key in _SUMMED_USAGE_KEYS:
            value = usage.get(key)
            if isinstance(value, int):
                self.usage[key] = self.usage.get(key, 0) + value

    def to_json(self) -> str:
        return json.dumps(
            {
                "chat_id": self.chat_id,
                "result": self.text,
                "is_error": self.error is not None,
                "error": self.error,
                "usage": self.usage,
                "denied_tools": self.denied_tools,
            }
        )


def _fail(message: str, code: int) -> typer.Exit:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return typer.Exit(code=code)


@contextmanager
def _backend(startup_timeout: float, keep_background: bool = False) -> Iterator[None]:
    """Use the running backend, or run one for the life of this command.

    A running backend keeps its own background commands; only a backend started
    here can be told to leave them running when the command ends.
    """
    from suzent.cli.main import (
        _is_suzent_server_running,
        _terminate_process_gracefully,
    )

    url = get_server_url()
    parts = urlsplit(url)
    host, port = parts.hostname or "127.0.0.1", parts.port or 80
    if _is_suzent_server_running(host, port, attempts=2):
        yield
        return
    if not _is_loopback_url(url):
        raise _fail(f"No Suzent server answers at {url}.", EXIT_RUN_FAILED)

    env = {**os.environ, "SUZENT_HOST": host, "SUZENT_PORT": str(port)}
    if keep_background:
        from suzent.tools.shell.host_process_registry import KEEP_BACKGROUND_ENV

        env[KEEP_BACKGROUND_ENV] = "1"
    # The reply owns stdout, so the server's own output goes to stderr.
    process = subprocess.Popen(
        [sys.executable, "-m", "suzent.server"], env=env, stdout=sys.stderr
    )
    try:
        deadline = time.monotonic() + startup_timeout
        while not _is_suzent_server_running(host, port):
            if process.poll() is not None:
                raise _fail(
                    f"The Suzent server exited with code {process.returncode} "
                    "while starting.",
                    EXIT_RUN_FAILED,
                )
            if time.monotonic() > deadline:
                raise _fail(
                    f"The Suzent server did not answer within {startup_timeout:.0f}s.",
                    EXIT_RUN_FAILED,
                )
            time.sleep(0.5)
        yield
    finally:
        _terminate_process_gracefully(process)


async def _chat_config(
    cwd: Path,
    model: str | None,
    permission_mode: str | None,
    tools: list[str] | None,
    code_mode: bool | None,
) -> dict[str, Any]:
    """Build the per-turn config binding the run to ``cwd``."""
    from suzent.acp.server import WORKSPACE_MOUNT

    settings = await get_client().config.get()
    if model and model not in settings.get("models", []):
        # The backend would otherwise fall back to another model without saying so.
        raise _fail(
            f"Model '{model}' is not enabled. Enabled models: "
            f"{', '.join(settings.get('models', [])) or 'none'}.",
            EXIT_USAGE,
        )
    if unknown := sorted(set(tools or []) - set(settings.get("tools", []))):
        raise _fail(
            f"Unknown tools: {', '.join(unknown)}. "
            f"Available tools: {', '.join(settings.get('tools', []))}.",
            EXIT_USAGE,
        )
    sandboxed = (settings.get("userPreferences") or {}).get("sandbox_enabled")
    if not isinstance(sandboxed, bool):
        sandboxed = bool(settings.get("sandboxEnabled"))

    config: dict[str, Any] = {
        "sandbox_volumes": [f"{cwd}:{WORKSPACE_MOUNT}"],
        "cwd": WORKSPACE_MOUNT if sandboxed else str(cwd),
        # Sent explicitly: the backend does not apply the saved preference to
        # a turn, so it could otherwise execute in the other mode than `cwd`.
        "sandbox_enabled": sandboxed,
        # Without this the question tool waits for an answer nobody can give.
        "interaction_profile": "headless",
        # The run names its own chat, so it skips the model call for a title.
        "auto_title": False,
    }
    if model:
        config["model"] = model
    if permission_mode:
        config["permission_mode"] = permission_mode
    if tools:
        config["tools"] = tools
        # A run that names its tools gets those and no others: the builtin
        # floor would add tools such as send_file that mean nothing to a script.
        config["exact_tools"] = True
    if code_mode is not None:
        config["code_mode"] = code_mode
    return config


async def _follow_stream(
    payload: dict[str, Any], result: RunResult, quiet: bool
) -> list[ApprovalRequest]:
    """Record one stream into ``result``; return the approvals it stopped on."""
    parser = StreamParser()
    pending: list[ApprovalRequest] = []

    def handle(event: object) -> None:
        match event:
            case TextChunk(content=content):
                result.text += content
                if not quiet:
                    typer.echo(content, nl=False)
            case ToolCall():
                # Name only: arguments can hold secrets, and stderr ends up
                # in CI and benchmark logs. The chat log keeps the full call.
                typer.echo(f"[tool] {event.tool_name}", err=True)
            case UsageUpdate(usage=usage):
                result.add_usage(usage)
            case ErrorEvent(message=message):
                result.error = message
            case ApprovalRequest():
                pending.append(event)

    async for chunk in get_client().chat.stream_message(payload, timeout=None):
        for event in parser.parse(iter([chunk])):
            handle(event)
    for event in parser.flush():
        handle(event)
    return pending


async def _run(prompt: str, config: dict[str, Any], quiet: bool) -> RunResult:
    """Send ``prompt`` and follow the stream to its end, denying any approval."""
    client = get_client()
    chat = await client.chat.create_chat(
        {"title": f"[run] {prompt[:40]}", "messages": [], "config": config}
    )
    result = RunResult(chat_id=chat["id"])
    resume_approvals: list[dict[str, Any]] = []

    while True:
        payload: dict[str, Any] = {
            "message": "" if resume_approvals else prompt,
            "chat_id": result.chat_id,
            "stream": True,
            "config": config,
        }
        if resume_approvals:
            payload["resume_approvals"] = resume_approvals

        pending = await _follow_stream(payload, result, quiet)
        if not pending or result.error:
            return result
        result.denied_tools.extend(request.tool_name for request in pending)
        resume_approvals = [
            {
                "request_id": request.request_id,
                "tool_call_id": request.tool_call_id,
                "approved": False,
            }
            for request in pending
        ]


def register_run_command(app: typer.Typer) -> None:
    """Attach the ``run`` command to the top-level CLI app."""

    @app.command("run")
    def run(
        prompt: str = typer.Argument(
            None, help="The task to run. Omit it to read the task from stdin"
        ),
        cwd: Path = typer.Option(
            None, "--cwd", help="Folder the agent works in (default: this folder)"
        ),
        model: str = typer.Option(
            None, "--model", "-m", help="Model to use (default: your default model)"
        ),
        permission_mode: str = typer.Option(
            None,
            "--permission-mode",
            help=(
                "Permission mode for this run (default: your saved mode). Nobody "
                "is there to approve, so a tool that would ask is denied; "
                "'full_access' never asks"
            ),
        ),
        tools: str = typer.Option(
            None,
            "--tools",
            help=(
                "Comma-separated tools the agent may use for this run "
                "(default: your saved tools). Only these tools are given"
            ),
        ),
        code_mode: bool = typer.Option(
            None,
            "--code-mode/--no-code-mode",
            help=(
                "Let the agent batch read-only tool calls in one code snippet "
                "(default: your saved setting)"
            ),
        ),
        as_json: bool = typer.Option(
            False,
            "--json",
            help="Print one JSON object (reply, token usage, chat id) when done",
        ),
        keep_background: bool = typer.Option(
            False,
            "--keep-background-processes",
            help=(
                "Leave commands the agent started in the background running "
                "after the run ends, such as a server the task asks for"
            ),
        ),
        startup_timeout: float = typer.Option(
            120.0,
            "--startup-timeout",
            help="Seconds to wait for a server this command has to start",
        ),
    ) -> None:
        """Run one task without a terminal session, then exit."""
        if prompt is None and not sys.stdin.isatty():
            prompt = sys.stdin.read()
        if not prompt or not prompt.strip():
            raise _fail("Give a task as an argument or on stdin.", EXIT_USAGE)
        if permission_mode is not None:
            # Imported here: the permission schema pulls in pydantic, which
            # every other `suzent` command would then pay for at startup.
            from suzent.permissions.models import PermissionMode

            modes = [mode.value for mode in PermissionMode]
            if permission_mode not in modes:
                raise _fail(
                    f"Unknown permission mode '{permission_mode}'. "
                    f"Expected one of: {', '.join(modes)}.",
                    EXIT_USAGE,
                )
        workdir = (cwd or Path.cwd()).resolve()
        if not workdir.is_dir():
            raise _fail(f"'{workdir}' is not a folder.", EXIT_USAGE)

        async def _execute() -> RunResult:
            tool_names = [name.strip() for name in (tools or "").split(",")]
            config = await _chat_config(
                workdir,
                model,
                permission_mode,
                [n for n in tool_names if n] or None,
                code_mode,
            )
            return await _run(prompt.strip(), config, quiet=as_json)

        with _backend(startup_timeout, keep_background):
            try:
                result = asyncio.run(_execute())
            except ClientError as e:
                raise _fail(str(e), EXIT_RUN_FAILED)

        if as_json:
            typer.echo(result.to_json())
        else:
            typer.echo("")
        if result.denied_tools:
            typer.secho(
                f"Denied without asking: {', '.join(result.denied_tools)}. "
                "Pass --permission-mode full_access to allow every tool.",
                fg=typer.colors.YELLOW,
                err=True,
            )
        if result.error:
            raise _fail(f"Run failed: {result.error}", EXIT_RUN_FAILED)
