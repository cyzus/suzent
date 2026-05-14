from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from suzent.logger import get_logger

logger = get_logger(__name__)

CodexSessionState = Literal[
    "connected",
    "not_installed",
    "not_logged_in",
    "api_key_login",
    "error",
]


class CodexSessionStatus(BaseModel):
    status: CodexSessionState
    connected: bool
    auth_mode: Literal["chatgpt", "api_key", "access_token"] | None = None
    executable: str | None = None
    codex_home: str
    message: str
    recovery_hint: str | None = None
    checked_at: str | None = None


class CodexCommandResult(BaseModel):
    success: bool
    message: str
    status: CodexSessionStatus | None = None


class CodexExecResult(BaseModel):
    success: bool
    output: str
    message: str
    returncode: int


class CodexSessionService:
    """Small wrapper around official Codex CLI auth commands.

    This service never reads or returns Codex token files. It treats the
    official CLI/keyring cache as the credential authority.
    """

    def __init__(
        self,
        *,
        executable: str | None = None,
        codex_home: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._executable_override = executable
        self._codex_home_override = codex_home
        self._timeout_seconds = timeout_seconds

    @property
    def codex_home(self) -> Path:
        configured = self._codex_home_override or os.environ.get("CODEX_HOME")
        if configured:
            return Path(configured).expanduser()
        return Path.home() / ".codex"

    def get_status(self) -> CodexSessionStatus:
        executable = self._resolve_executable()
        codex_home = str(self.codex_home)
        if executable is None:
            return CodexSessionStatus(
                status="not_installed",
                connected=False,
                executable=None,
                codex_home=codex_home,
                message="Codex CLI is not installed or is not available on PATH.",
                recovery_hint="Install the official Codex CLI, then run codex login.",
            )

        result = self._run(["login", "status"], executable=executable)
        output = self._combined_output(result)
        lowered = output.lower()

        if result.returncode == 0 and "logged in using chatgpt" in lowered:
            return CodexSessionStatus(
                status="connected",
                connected=True,
                auth_mode="chatgpt",
                executable=executable,
                codex_home=codex_home,
                message="Codex is logged in using ChatGPT.",
            )

        if result.returncode == 0 and "logged in using an api key" in lowered:
            return CodexSessionStatus(
                status="api_key_login",
                connected=False,
                auth_mode="api_key",
                executable=executable,
                codex_home=codex_home,
                message="Codex is logged in using an API key, not a ChatGPT subscription session.",
                recovery_hint="Run codex logout, then codex login and choose ChatGPT sign-in.",
            )

        if result.returncode == 0 and "logged in using access token" in lowered:
            return CodexSessionStatus(
                status="connected",
                connected=True,
                auth_mode="access_token",
                executable=executable,
                codex_home=codex_home,
                message="Codex is logged in using an access token.",
                recovery_hint="For subscription access, prefer ChatGPT sign-in unless this token is managed by your organization.",
            )

        if "not logged in" in lowered:
            return CodexSessionStatus(
                status="not_logged_in",
                connected=False,
                executable=executable,
                codex_home=codex_home,
                message="Codex is installed but not logged in.",
                recovery_hint="Run codex login and choose ChatGPT sign-in.",
            )

        return CodexSessionStatus(
            status="error",
            connected=False,
            executable=executable,
            codex_home=codex_home,
            message=self._safe_error_message(output)
            or "Could not determine Codex login status.",
            recovery_hint="Run codex login status in a terminal for details.",
        )

    def start_login(self, *, device_auth: bool = False) -> CodexCommandResult:
        executable = self._resolve_executable()
        if executable is None:
            return CodexCommandResult(
                success=False,
                message="Codex CLI is not installed or is not available on PATH.",
                status=self.get_status(),
            )

        args = ["login"]
        if device_auth:
            args.append("--device-auth")

        try:
            creationflags = (
                getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if os.name == "nt" else 0
            )
            subprocess.Popen(
                [executable, *args],
                cwd=str(Path.home()),
                env=self._env(),
                close_fds=True,
                creationflags=creationflags,
            )
        except Exception as exc:
            logger.warning("Failed to start Codex login: {}", exc)
            return CodexCommandResult(
                success=False,
                message="Failed to start Codex login.",
                status=self.get_status(),
            )

        mode = "device-code" if device_auth else "browser"
        return CodexCommandResult(
            success=True,
            message=f"Started Codex {mode} login. Complete the flow in the opened Codex process.",
            status=self.get_status(),
        )

    def logout(self) -> CodexCommandResult:
        executable = self._resolve_executable()
        if executable is None:
            return CodexCommandResult(
                success=False,
                message="Codex CLI is not installed or is not available on PATH.",
                status=self.get_status(),
            )

        result = self._run(["logout"], executable=executable)
        if result.returncode == 0:
            return CodexCommandResult(
                success=True,
                message="Codex logout completed.",
                status=self.get_status(),
            )

        output = self._safe_error_message(self._combined_output(result))
        return CodexCommandResult(
            success=False,
            message=output or "Codex logout failed.",
            status=self.get_status(),
        )

    def exec_prompt(
        self,
        prompt: str,
        *,
        model: str | None = None,
        cwd: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> CodexExecResult:
        """Run one non-interactive Codex turn using the official CLI login."""
        status = self.get_status()
        if not status.connected or status.auth_mode != "chatgpt":
            return CodexExecResult(
                success=False,
                output="",
                message=status.recovery_hint or status.message,
                returncode=1,
            )

        executable = self._resolve_executable()
        if executable is None:
            return CodexExecResult(
                success=False,
                output="",
                message="Codex CLI is not installed or is not available on PATH.",
                returncode=1,
            )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as output_file:
            output_path = output_file.name

        args = [
            "exec",
            "-c",
            'approval_policy="never"',
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "--output-last-message",
            output_path,
        ]
        if model:
            args.extend(["--model", model])
        if cwd:
            args.extend(["--cd", cwd])
        args.append("-")

        try:
            result = subprocess.run(
                [executable, *args],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=self._env(),
                check=False,
            )
            output = ""
            try:
                output = Path(output_path).read_text(encoding="utf-8").strip()
            except Exception:
                output = ""
            if not output:
                output = (result.stdout or "").strip()

            if result.returncode == 0 and output:
                return CodexExecResult(
                    success=True,
                    output=output,
                    message="Codex execution completed.",
                    returncode=0,
                )

            error = self._codex_exec_error_message(result)
            return CodexExecResult(
                success=False,
                output=output,
                message=error or "Codex execution failed.",
                returncode=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return CodexExecResult(
                success=False,
                output="",
                message="Codex execution timed out.",
                returncode=124,
            )
        finally:
            try:
                Path(output_path).unlink(missing_ok=True)
            except Exception:
                pass

    def _resolve_executable(self) -> str | None:
        if self._executable_override:
            return self._executable_override
        return shutil.which("codex")

    def _run(
        self, args: list[str], *, executable: str
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [executable, *args],
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                env=self._env(),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(
                [executable, *args],
                returncode=124,
                stdout="",
                stderr="Codex command timed out.",
            )
        except Exception as exc:
            return subprocess.CompletedProcess(
                [executable, *args],
                returncode=1,
                stdout="",
                stderr=str(exc),
            )

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["CODEX_HOME"] = str(self.codex_home)
        return env

    @staticmethod
    def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
        return "\n".join(part for part in (result.stdout, result.stderr) if part).strip()

    @staticmethod
    def _safe_error_message(output: str) -> str:
        # Keep only the first line; Codex auth failures can include diagnostics,
        # but endpoint responses should not echo raw local logs or secrets.
        return output.strip().splitlines()[0] if output.strip() else ""

    @classmethod
    def _codex_exec_error_message(cls, result: subprocess.CompletedProcess[str]) -> str:
        output = cls._combined_output(result)
        for line in output.splitlines():
            if not line.startswith("ERROR:"):
                continue
            payload = line.removeprefix("ERROR:").strip()
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                return payload
            message = data.get("error", {}).get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        return cls._safe_error_message(output)


def get_codex_session_service(codex_home: str | None = None) -> CodexSessionService:
    return CodexSessionService(codex_home=codex_home)
