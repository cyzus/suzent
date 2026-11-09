"""Run the agent-desktop CLI on the host and read its JSON envelope.

The per-chat Docker sandbox has no display, so this module never sends the
command there. It execs the binary in the Suzent backend process, which is
the user's graphical session, and it never invokes a shell.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
from dataclasses import dataclass
from typing import Any

from suzent.logger import get_logger
from suzent.plugins.binaries import PluginBinary

logger = get_logger(__name__)

INSTALL_HINT = (
    "agent-desktop 1.x is not available. Suzent can download the release "
    "pinned in the Desktop plugin after you agree. In Settings → Plugins, choose Install "
    "agent-desktop on the Desktop plugin, or run `suzent plugin install desktop`.\n"
    "You can also install it yourself (`npm install -g agent-desktop`) or set "
    "SUZENT_AGENT_DESKTOP_BIN to an executable you already have.\n"
    "On macOS, grant Accessibility permission with:\n"
    "  agent-desktop permissions --guide\n"
    "On Windows the official binary is unsigned. SmartScreen, antivirus, or "
    "Smart App Control may block it."
)

_RELEASE = re.compile(r"^1\.\d+\.\d+(?:[-+].+)?$")
_STDOUT_LIMIT = 16 * 1024 * 1024
_support_lock = asyncio.Lock()
_supported: set[str] = set()
_binary: PluginBinary | None = None


class DesktopBinaryError(Exception):
    """The agent-desktop executable is missing or not runnable."""


class DesktopTimeout(Exception):
    """The CLI did not exit within the budget for this command."""


@dataclass(frozen=True)
class RenderedEnvelope:
    ok: bool
    message: str
    metadata: dict[str, Any]
    error_code: str | None


def is_supported_release(version: str) -> bool:
    """True for agent-desktop 1.x, the major version this plugin was written against."""
    return bool(_RELEASE.fullmatch(version.strip()))


def use_binary(handle: PluginBinary) -> None:
    """Set by the plugin's ``register`` from its ``plugin.yaml`` declaration."""
    global _binary
    _binary = handle


def resolve_binary() -> str:
    """Return the host executable. This never downloads or installs it.

    An explicit ``SUZENT_AGENT_DESKTOP_BIN`` wins, then the copy Suzent
    installed after consent, then whatever ``agent-desktop`` is on PATH.
    """
    if _binary is None:
        raise DesktopBinaryError(INSTALL_HINT)
    located = _binary.locate()
    if located is None:
        override = os.environ.get("SUZENT_AGENT_DESKTOP_BIN", "").strip()
        if override:
            raise DesktopBinaryError(
                f"SUZENT_AGENT_DESKTOP_BIN is {override}, which is not an "
                f"executable file.\n{INSTALL_HINT}"
            )
        raise DesktopBinaryError(INSTALL_HINT)
    return str(located[0])


def reset_binary_cache() -> None:
    """Forget which binaries have already passed the version check."""
    _supported.clear()


def parse_envelope(stdout: str) -> dict[str, Any]:
    """Parse the one JSON object agent-desktop writes to stdout."""
    text = stdout.strip()
    if not text:
        raise ValueError("agent-desktop returned no JSON on stdout")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"agent-desktop stdout was not a JSON envelope: {exc}"
        ) from exc
    if not isinstance(value, dict) or "ok" not in value:
        raise ValueError("agent-desktop stdout was not a JSON envelope")
    return value


def render_envelope(envelope: dict[str, Any]) -> RenderedEnvelope:
    """Turn an envelope into text for the model, without inlined image bytes."""
    command = str(envelope.get("command") or "")
    if envelope.get("ok") is True:
        data = _shrink(envelope.get("data"))
        payload = {"ok": True, "command": command, "data": data}
        lines: list[str] = []
        if isinstance(data, dict):
            disposition = data.get("disposition")
            if isinstance(disposition, dict) and disposition.get("delivery"):
                lines.append(
                    "delivery="
                    f"{disposition.get('delivery')} retry={disposition.get('retry')}. "
                    "ok means the command returned, not that the app committed the "
                    "effect. Snapshot again to check. Repeat an action only when "
                    "retry is safe."
                )
            if data.get("complete") is False:
                lines.append(
                    "This snapshot is partial (complete is false). "
                    "Do not treat a missing element as absent."
                )
        lines.append(json.dumps(payload, ensure_ascii=False, indent=2))
        return RenderedEnvelope(
            True,
            "\n".join(lines),
            {"command": command, "host_execution": True},
            None,
        )

    error = envelope.get("error") if isinstance(envelope.get("error"), dict) else {}
    code = str(error.get("code") or "INTERNAL")
    disposition = (
        error.get("disposition") if isinstance(error.get("disposition"), dict) else {}
    )
    lines = [f"agent-desktop {command or 'command'} failed: {code}."]
    if disposition.get("retry"):
        lines.append(
            f"retry={disposition['retry']} "
            f"delivery={disposition.get('delivery', 'unknown')}. "
            "Repeat the action only when retry is safe."
        )
    suggestion = error.get("suggestion")
    if isinstance(suggestion, str) and suggestion.strip():
        lines.append(f"suggestion: {suggestion.strip()}")
    recovery = error.get("recovery")
    if isinstance(recovery, dict) and recovery.get("strategy"):
        lines.append(f"recovery: {recovery['strategy']}")
    shown = dict(envelope)
    if "error" in shown:
        shown["error"] = _shrink(shown["error"])
    lines.append(json.dumps(shown, ensure_ascii=False, indent=2))
    return RenderedEnvelope(
        False,
        "\n".join(lines),
        {
            "command": command,
            "error_code": code,
            "retry": disposition.get("retry"),
            "host_execution": True,
        },
        code,
    )


async def ensure_supported_binary(binary: str) -> str | None:
    """Return an error when ``binary`` is not agent-desktop 1.x.

    A successful check is remembered. A failure is not, so installing the
    right binary takes effect on the next call without a restart.
    """
    async with _support_lock:
        if binary in _supported:
            return None
        try:
            _code, stdout, _stderr = await run_cli(binary, ["version"], timeout=20)
            envelope = parse_envelope(stdout)
        except (OSError, DesktopTimeout, ValueError) as exc:
            return f"Could not read the agent-desktop version: {exc}"
        data = envelope.get("data") if envelope.get("ok") is True else None
        version = data.get("version") if isinstance(data, dict) else None
        if not isinstance(version, str) or not is_supported_release(version):
            shown = version if isinstance(version, str) else "an unreadable version"
            return (
                "Suzent's desktop plugin supports agent-desktop 1.x. "
                f"This binary reported {shown}. Install a 1.x release from "
                "https://github.com/vercel-labs/agent-desktop/releases"
            )
        _supported.add(binary)
        return None


async def run_cli(
    binary: str, argv: list[str], *, timeout: float
) -> tuple[int, str, str]:
    """Exec ``binary`` with ``argv`` on the host. ``argv`` is not a shell line."""
    command_name = next((part for part in argv if not part.startswith("-")), "?")
    logger.debug("Running host agent-desktop command {}", command_name)
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    try:
        process = await asyncio.create_subprocess_exec(
            binary,
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
            limit=_STDOUT_LIMIT,
            **kwargs,
        )
    except FileNotFoundError as exc:
        raise DesktopBinaryError(INSTALL_HINT) from exc
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
    except BaseException as exc:
        # Cancellation (and every other failure) must reap the host process.
        # On 3.11+ a cancelled task cannot await until its cancel count is
        # cleared, so the wait below would otherwise be skipped and the CLI
        # would keep acting on the desktop with no timeout left.
        await _stop_process(process)
        if isinstance(exc, TimeoutError):
            raise DesktopTimeout(
                f"agent-desktop {command_name} did not finish within {timeout:.0f}s"
            ) from exc
        if isinstance(exc, asyncio.LimitOverrunError):
            raise ValueError(
                "agent-desktop output was too large. For a screenshot, pass options.path "
                "so the image is written to a file instead of returned inline."
            ) from exc
        raise
    return (
        process.returncode if process.returncode is not None else 1,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    """Kill the CLI and wait until it has exited, even if this task is cancelled."""
    task = asyncio.current_task()
    pending = task.cancelling() if task is not None else 0
    if task is not None:
        while task.cancelling():
            task.uncancel()
    try:
        if process.returncode is None:
            _kill(process)
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                process.kill()
                await process.wait()
    finally:
        if task is not None:
            for _ in range(pending):
                task.cancel()


def _kill(process: asyncio.subprocess.Process) -> None:
    """Stop the CLI process group.

    On POSIX the CLI is started in its own session, so this reaches children
    that have not daemonized. Timeout and cancellation both come through here.
    """
    if process.returncode is not None or process.pid is None:
        return
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except ProcessLookupError:
            return
    process.kill()


def _shrink(value: Any) -> Any:
    """Drop inlined image payloads. The accessibility tree stays intact."""
    if isinstance(value, dict):
        shrunk: dict[str, Any] = {}
        for key, item in value.items():
            if key == "data" and isinstance(item, str) and len(item) > 256:
                shrunk[key] = (
                    f"[omitted {len(item)} characters; pass options.path "
                    "to save the image to a file]"
                )
            else:
                shrunk[key] = _shrink(item)
        return shrunk
    if isinstance(value, list):
        return [_shrink(item) for item in value]
    return value
