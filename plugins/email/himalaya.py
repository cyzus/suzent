"""Run the himalaya CLI against one mailbox account.

Each run gets a throwaway configuration describing that account alone. The
file holds no secret: himalaya asks for the password through a command that
prints it from an environment variable set on the himalaya process only, so
the password never lands on disk and never enters Suzent's own environment.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from suzent.logger import get_logger
from suzent.plugins.binaries import PluginBinary

from .accounts import MailAccount

logger = get_logger(__name__)

TIMEOUT_SECONDS = 90
_SECRET_ENV = "SUZENT_MAIL_SECRET"
_PRINT_SECRET = f"import os,sys;sys.stdout.write(os.environ['{_SECRET_ENV}'])"

_binary: PluginBinary | None = None


def use_binary(binary: PluginBinary) -> None:
    global _binary
    _binary = binary


class MailError(Exception):
    """A mailbox operation failed; the message is fit to show the agent."""


def _toml(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml(v) for v in value) + "]"
    # JSON string escapes are valid TOML basic-string escapes.
    return json.dumps(str(value), ensure_ascii=False)


def _server(scheme: str, host: str, port: int) -> str:
    return f"{scheme}://{host}:{port}"


def config_toml(account: MailAccount, python: str = sys.executable) -> str:
    secret_command = [python, "-c", _PRINT_SECRET]
    smtp_scheme = "smtps" if account.smtp_security == "ssl" else "smtp"
    auth_mechanism = "xoauth2" if account.auth_type == "xoauth2" else "plain"
    secret_field = "token" if account.auth_type == "xoauth2" else "password"
    settings: list[tuple[str, Any]] = [
        ("default", True),
        ("email", account.email),
        ("imap.server", _server("imaps", account.imap_host, account.imap_port)),
        (f"imap.sasl.{auth_mechanism}.username", account.login),
        (f"imap.sasl.{auth_mechanism}.{secret_field}.command", secret_command),
        ("smtp.server", _server(smtp_scheme, account.smtp_host, account.smtp_port)),
        (f"smtp.sasl.{auth_mechanism}.username", account.login),
        (f"smtp.sasl.{auth_mechanism}.{secret_field}.command", secret_command),
    ]
    if account.display_name:
        settings.append(("display-name", account.display_name))
    if account.smtp_security == "starttls":
        settings.append(("smtp.starttls", True))
    if account.needs_imap_id:
        settings.append(("imap.id.auto", True))
    if account.no_sasl_ir:
        settings.append(("imap.sasl-ir", False))
    lines = ["[accounts.suzent]"]
    lines += [f"{key} = {_toml(value)}" for key, value in settings]
    return "\n".join(lines) + "\n"


def _executable() -> Path:
    if _binary is None:
        raise MailError("The email plugin is not loaded.")
    found = _binary.locate()
    if found is None:
        raise MailError(
            "The himalaya mail client is not installed. Ask the user to install "
            "it from Settings → Services → Email."
        )
    return found[0]


def _error_text(stdout: bytes, stderr: bytes) -> str:
    for stream in (stdout, stderr):
        text = stream.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        try:
            data = json.loads(text)
        except ValueError:
            return text.splitlines()[-1][:500]
        if isinstance(data, dict) and data.get("error"):
            return str(data["error"])[:500]
    return "himalaya failed without a message"


async def run(
    account: MailAccount,
    password: str,
    args: list[str],
    *,
    stdin: bytes | None = None,
    json_output: bool = True,
    timeout: float = TIMEOUT_SECONDS,
) -> Any:
    """Run one himalaya command; parsed JSON, or raw stdout when json_output is off."""
    executable = _executable()
    env = {**os.environ, _SECRET_ENV: password}
    env.pop("HIMALAYA_CONFIG", None)
    with tempfile.TemporaryDirectory(prefix="suzent-mail-") as workdir:
        Path(workdir, "config.toml").write_text(config_toml(account), encoding="utf-8")
        # A relative path: himalaya splits -c on ':', which breaks C:\ paths.
        command = [str(executable), "-c", "config.toml", *args]
        if json_output:
            command.insert(3, "--json")
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=workdir,
            env=env,
            stdin=asyncio.subprocess.PIPE
            if stdin is not None
            else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(stdin), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise MailError(
                f"{account.imap_host} did not answer within {int(timeout)} seconds."
            ) from None
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise
    if process.returncode != 0:
        message = _error_text(stdout, stderr)
        logger.debug(f"himalaya {args[:2]} failed: {message}")
        raise MailError(message)
    if not json_output:
        return stdout
    try:
        return json.loads(stdout.decode("utf-8") or "null")
    except ValueError as exc:
        raise MailError("himalaya returned output Suzent could not read") from exc
