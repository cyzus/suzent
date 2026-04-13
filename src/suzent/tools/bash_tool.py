"""
BashTool for Agent
==================

Provides code execution within agent conversations.
Each chat session gets its own session with persistent storage.

Supports two modes:
- Sandbox mode: Execute in isolated Docker container (requires Docker Desktop)
- Host mode: Execute directly on host machine (restricted to workspace)
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Annotated, Literal, Optional

from pydantic import Field
from pydantic_ai import RunContext
from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

from suzent.logger import get_logger

logger = get_logger(__name__)


class BashTool(Tool):
    """
    Execute code in an isolated sandbox environment.

    Features:
    - Supports Python, Node.js, and shell commands
    - Persistent storage at /persistence (survives restarts)
    - Shared storage at /shared (accessible by all sessions)
    - Internet access for package installation and API calls
    """

    name = "BashTool"
    tool_name = "bash_execute"
    group = ToolGroup.EXECUTION
    requires_approval = True
    session_guidance = (
        "Reserve BashTool for shell/system execution. Prefer dedicated file tools "
        "for read/search/edit operations when available."
    )
    guidance_priority = 10
    _SUPPORTED_LANGUAGES = {"python", "nodejs", "command"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._manager = None
        self.chat_id: Optional[str] = None
        self.custom_volumes: Optional[list] = None
        self.sandbox_enabled: bool = True
        self.workspace_root: Optional[str] = None
        self.cwd: Optional[str] = None

    @property
    def manager(self):
        """Lazy-load sandbox manager with custom volumes if set."""
        if self._manager is None:
            from suzent.sandbox import SandboxManager

            # Pass custom volumes if they were set (per-chat config)
            if self.custom_volumes is not None:
                self._manager = SandboxManager(custom_volumes=self.custom_volumes)
            else:
                self._manager = SandboxManager()
        return self._manager

    def set_custom_volumes(self, volumes: list):
        """Set custom volume mounts from per-chat config."""
        self.custom_volumes = volumes
        # Clear cached manager so it recreates with new volumes
        self._manager = None

    def _execution_metadata(
        self,
        mode: str,
        language: str,
        timeout: Optional[int],
        background: bool,
        **extra,
    ) -> dict:
        metadata = {
            "mode": mode,
            "language": language,
            "timeout": timeout,
            "background": background,
        }
        metadata.update(extra)
        return metadata

    def _success_result(
        self,
        message: str,
        mode: str,
        language: str,
        timeout: Optional[int],
        background: bool,
        **extra,
    ) -> ToolResult:
        return ToolResult.success_result(
            message,
            metadata=self._execution_metadata(
                mode, language, timeout, background, **extra
            ),
        )

    def _error_result(
        self,
        error_code: ToolErrorCode,
        message: str,
        mode: str,
        language: str,
        timeout: Optional[int],
        background: bool,
        **extra,
    ) -> ToolResult:
        return ToolResult.error_result(
            error_code,
            message,
            metadata=self._execution_metadata(
                mode, language, timeout, background, **extra
            ),
        )

    def _audit_execution(self, status: str, **kwargs):
        self.audit_operation(self.tool_name, "execute", status, **kwargs)

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        content: Annotated[
            str,
            Field(
                description=(
                    "Code or command text to execute. This is a full replacement "
                    "command, not a patch."
                )
            ),
        ],
        language: Annotated[
            Literal["python", "nodejs", "command"],
            Field(description="Execution mode for the content."),
        ] = "command",
        timeout: Annotated[
            Optional[int],
            Field(
                default=None,
                ge=0,
                description=(
                    "Optional execution timeout in seconds. Use background=True "
                    "for long-running work."
                ),
            ),
        ] = None,
        background: Annotated[
            bool,
            Field(
                description=(
                    "Run the command in the background and return a process_id "
                    "instead of waiting for completion."
                )
            ),
        ] = False,
    ) -> ToolResult:
        """Execute code or command in a secure environment (sandbox or host mode).

        Supported languages:
        - python: Execute Python code
        - nodejs: Execute Node.js code
        - command: Execute shell commands

        Storage paths:
        - In sandbox mode, /persistence is the private per-chat mount and /shared is the shared mount.
        - In host mode, the same locations are exposed through environment variables instead of container mounts.
        - Custom mounts are still available in both modes through per-chat volume configuration.

        In host mode (non-sandbox), these environment variables are available:
        - WORKSPACE_ROOT: The workspace directory
        - PERSISTENCE_PATH: The resolved persistence directory path
        - SHARED_PATH: The resolved shared directory path
        - CHAT_ID: The current chat/session identifier
        - MOUNT_*: Custom volume paths (e.g., MOUNT_SKILLS for /mnt/skills)

        Returns the execution output or error message.

        Args:
            ctx: The pydantic-ai run context with agent dependencies.
            content: The code or shell command to execute.
            language: Execution language: 'python', 'nodejs', or 'command'. Defaults to 'command'.
            timeout: Execution timeout in seconds (optional). For long-running tasks, use background=True instead.
            background: If True, run in background and return a process_id. Use ProcessTool to poll/kill.
        """
        self.chat_id = ctx.deps.chat_id
        self.sandbox_enabled = ctx.deps.sandbox_enabled
        self.workspace_root = ctx.deps.workspace_root
        self.cwd = getattr(ctx.deps, "cwd", None)
        if ctx.deps.custom_volumes and ctx.deps.custom_volumes != self.custom_volumes:
            self.set_custom_volumes(ctx.deps.custom_volumes)

        if not self.chat_id:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "No chat context. Cannot determine execution session.",
            )

        denied_reason = self.is_tool_denied(ctx.deps, self.tool_name)
        if denied_reason:
            self.audit_operation(
                self.tool_name,
                "execute",
                "denied",
                language=language,
                background=background,
                reason=denied_reason,
            )
            return self._error_result(
                ToolErrorCode.PERMISSION_DENIED,
                denied_reason,
                mode="unknown",
                language=language,
                timeout=timeout,
                background=background,
            )

        lang = language.strip().lower()
        if lang not in self._SUPPORTED_LANGUAGES:
            self.audit_operation(
                self.tool_name,
                "execute",
                "rejected",
                language=lang,
                background=background,
                reason="unsupported_language",
            )
            return self._error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                (
                    f"Unsupported language '{language}'. "
                    "Use 'python', 'nodejs', or 'command'."
                ),
                mode="unknown",
                language=lang,
                timeout=timeout,
                background=background,
            )

        if background:
            if not self.sandbox_enabled:
                return self._error_result(
                    ToolErrorCode.INVALID_ARGUMENT,
                    "background=True requires sandbox mode.",
                    mode="sandbox",
                    language=lang,
                    timeout=timeout,
                    background=background,
                )
            return self._execute_background(content, lang)

        if self.sandbox_enabled:
            return self._execute_in_sandbox(content, lang, timeout)
        return self._execute_on_host(content, lang, timeout)

    def _execute_background(self, content: str, language: str) -> ToolResult:
        """Start a background process and return its process_id."""
        try:
            proc_id = self.manager.start_background(
                session_id=self.chat_id,
                content=content,
                language=language,
            )
            self._audit_execution(
                "background",
                language=language,
                process_id=proc_id,
            )
            return self._success_result(
                "Background process started.",
                mode="sandbox",
                language=language,
                timeout=None,
                background=True,
                process_id=proc_id,
            )
        except Exception as e:
            logger.error(f"Background execution error: {e}")
            self._audit_execution(
                "background",
                language=language,
                error=str(e),
            )
            return self._error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Error starting background process: {e}",
                mode="sandbox",
                language=language,
                timeout=None,
                background=True,
            )

    def _execute_in_sandbox(
        self,
        content: str,
        language: str,
        timeout: Optional[int] = None,
    ) -> ToolResult:
        """Execute code in isolated Docker sandbox."""
        try:
            # Manager is now synchronous - no async needed
            result = self.manager.execute(
                session_id=self.chat_id,
                content=content,
                language=language,
                timeout=timeout,
            )

            if result.success:
                output = result.output or "(no output)"
                logger.info(
                    f"Sandbox execution successful [{language}] for chat {self.chat_id}"
                )
                self._audit_execution(
                    "success",
                    mode="sandbox",
                    language=language,
                    timeout=timeout,
                    background=False,
                )
                return self._success_result(
                    output,
                    mode="sandbox",
                    language=language,
                    timeout=timeout,
                    background=False,
                )
            else:
                logger.warning(f"Sandbox execution error: {result.error}")
                self._audit_execution(
                    "error",
                    mode="sandbox",
                    language=language,
                    timeout=timeout,
                    background=False,
                    error=result.error,
                )
                return self._error_result(
                    ToolErrorCode.EXECUTION_FAILED,
                    f"Execution Error: {result.error}",
                    mode="sandbox",
                    language=language,
                    timeout=timeout,
                    background=False,
                )

        except Exception as e:
            logger.error(f"Sandbox tool error: {e}")
            self._audit_execution(
                "error",
                mode="sandbox",
                language=language,
                timeout=timeout,
                background=False,
                error=str(e),
            )
            return self._error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Sandbox Error: {str(e)}",
                mode="sandbox",
                language=language,
                timeout=timeout,
                background=False,
            )

    def _execute_on_host(
        self,
        content: str,
        language: str,
        timeout: Optional[int] = None,
    ) -> ToolResult:
        """Execute code directly on host machine, restricted to workspace."""
        if not self.workspace_root:
            return self._error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "workspace_root not configured for host execution",
                mode="host",
                language=language,
                timeout=timeout,
                background=False,
            )

        if language == "python":
            cmd = ["python", "-c", content]
        elif language == "nodejs":
            cmd = ["node", "-e", content]
        elif language == "command" and os.name == "nt":
            # Force PowerShell to output UTF-8 so non-ASCII characters
            # (e.g. localized adapter names) are captured correctly.
            utf8_preamble = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            cmd = ["powershell", "-NoProfile", "-Command", utf8_preamble + content]
        else:
            cmd = ["bash", "-c", content]

        effective_timeout = timeout or 120

        from suzent.config import CONFIG

        if self.cwd:
            working_dir = Path(self.cwd).resolve()
            working_dir.mkdir(parents=True, exist_ok=True)
        else:
            sandbox_data_path = Path(CONFIG.sandbox_data_path).resolve()
            working_dir = sandbox_data_path / "sessions" / self.chat_id
            working_dir.mkdir(parents=True, exist_ok=True)

        try:
            result = subprocess.run(
                cmd,
                cwd=str(working_dir),  # Working directory is /persistence equivalent
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=effective_timeout,
                env=self._get_host_env(),
            )

            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"

            logger.info(
                f"Host execution successful [{language}] for chat {self.chat_id}"
            )
            self._audit_execution(
                "success",
                mode="host",
                language=language,
                timeout=effective_timeout,
                background=False,
                returncode=result.returncode,
            )
            return self._success_result(
                output if output.strip() else "(no output)",
                mode="host",
                language=language,
                timeout=effective_timeout,
                background=False,
                returncode=result.returncode,
                cwd=str(working_dir),
            )

        except subprocess.TimeoutExpired:
            logger.warning(f"Host execution timed out after {effective_timeout}s")
            self._audit_execution(
                "timeout",
                mode="host",
                language=language,
                timeout=effective_timeout,
                background=False,
            )
            return self._error_result(
                ToolErrorCode.TIMEOUT,
                f"Command timed out after {effective_timeout} seconds",
                mode="host",
                language=language,
                timeout=effective_timeout,
                background=False,
            )
        except FileNotFoundError as e:
            logger.error(f"Host execution command not found: {e}")
            self._audit_execution(
                "error",
                mode="host",
                language=language,
                timeout=effective_timeout,
                background=False,
                error=str(e),
            )
            return self._error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Command not found - {e}",
                mode="host",
                language=language,
                timeout=effective_timeout,
                background=False,
            )
        except Exception as e:
            logger.error(f"Host execution error: {e}")
            self._audit_execution(
                "error",
                mode="host",
                language=language,
                timeout=effective_timeout,
                background=False,
                error=str(e),
            )
            return self._error_result(
                ToolErrorCode.EXECUTION_FAILED,
                str(e),
                mode="host",
                language=language,
                timeout=effective_timeout,
                background=False,
            )

    def _get_host_env(self) -> dict:
        """Build environment variables for host execution."""
        from suzent.config import CONFIG

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["WORKSPACE_ROOT"] = str(Path(self.workspace_root).resolve())

        sandbox_data_path = Path(CONFIG.sandbox_data_path).resolve()
        if self.chat_id:
            env["CHAT_ID"] = self.chat_id
            env["PERSISTENCE_PATH"] = str(sandbox_data_path / "sessions" / self.chat_id)
        env["SHARED_PATH"] = str(sandbox_data_path / "shared")

        if self.custom_volumes:
            from suzent.tools.filesystem.path_resolver import PathResolver

            for mount_str in self.custom_volumes:
                parsed = PathResolver.parse_volume_string(mount_str)
                if parsed:
                    host_path, container_path = parsed
                    # Convert /mnt/skills -> MOUNT_SKILLS
                    env_name = container_path.replace("/", "_").strip("_").upper()
                    if env_name.startswith("MNT_"):
                        env_name = "MOUNT_" + env_name[4:]
                    env[env_name] = str(Path(host_path).resolve())

        return env
