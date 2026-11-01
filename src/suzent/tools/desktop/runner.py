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
import shutil
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from suzent.logger import get_logger

logger = get_logger(__name__)

INSTALL_HINT = (
    "agent-desktop is not installed or not on PATH. Suzent does not install it "
    "for you. Install the 1.0.x CLI, then try again:\n"
    "  npm install -g agent-desktop\n"
    "Or download the release binary for your OS from\n"
    "  https://github.com/vercel-labs/agent-desktop/releases\n"
    "and put it on PATH, keeping the platform helper beside the executable.\n"
    "On macOS, grant Accessibility permission with:\n"
    "  agent-desktop permissions --guide\n"
    "If the binary lives somewhere else, set SUZENT_AGENT_DESKTOP_BIN to its path."
)

HOST_BANNER = (
    "Ran on the host desktop. agent-desktop is never executed inside the "
    "chat's Docker sandbox, which has no display."
)

_RELEASE = re.compile(r"^1\.0\.\d+(?:[-+].+)?$")
_STDOUT_LIMIT = 16 * 1024 * 1024
_support_lock = asyncio.Lock()
_supported: set[str] = set()


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
    """True for agent-desktop 1.0.x, the contract this plugin was written against."""
    return bool(_RELEASE.fullmatch(version.strip()))


def resolve_binary() -> str:
    """Return the host executable. Never downloads or installs it."""
    override = os.environ.get("SUZENT_AGENT_DESKTOP_BIN", "").strip()
    if override:
        path = Path(override).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        raise DesktopBinaryError(
            f"SUZENT_AGENT_DESKTOP_BIN is {override}, which is not an executable file.\n"
            f"{INSTALL_HINT}"
        )
    found = shutil.which("agent-desktop")
    if found:
        return found
    raise DesktopBinaryError(INSTALL_HINT)


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
        lines = [HOST_BANNER]
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
    lines = [
        HOST_BANNER,
        f"agent-desktop {command or 'command'} failed: {code}.",
        "retry="
        f"{disposition.get('retry', 'unknown')} "
        f"delivery={disposition.get('delivery', 'unknown')}. "
        "Repeat the action only when retry is safe.",
    ]
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
    """Return an error when ``binary`` is not agent-desktop 1.0.x.

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
                "Suzent's desktop plugin supports agent-desktop 1.0.x. "
                f"This binary reported {shown}. Install a 1.0.x release from "
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
    except TimeoutError as exc:
        _kill(process)
        try:
            await asyncio.wait_for(process.wait(), 5)
        except TimeoutError:
            process.kill()
        raise DesktopTimeout(
            f"agent-desktop {command_name} did not finish within {timeout:.0f}s"
        ) from exc
    except asyncio.LimitOverrunError as exc:
        _kill(process)
        await process.wait()
        raise ValueError(
            "agent-desktop output was too large. For a screenshot, pass options.path "
            "so the image is written to a file instead of returned inline."
        ) from exc
    return (
        process.returncode if process.returncode is not None else 1,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


def _kill(process: asyncio.subprocess.Process) -> None:
    """Stop a command that missed its deadline.

    On POSIX the CLI is started in its own session, so this reaches children
    that have not daemonized. A timeout is the only time that session is killed.
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
