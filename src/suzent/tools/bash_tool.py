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
from typing import Optional

from pydantic_ai import RunContext
from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool

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
    requires_approval = True
    _SUPPORTED_LANGUAGES = {"python", "nodejs", "command"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._manager = None
        self.chat_id: Optional[str] = None
        self.custom_volumes: Optional[list] = None
        self.sandbox_enabled: bool = True
        self.workspace_root: Optional[str] = None

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

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        content: str,
        language: Optional[str] = None,
        timeout: Optional[int] = None,
        background: bool = False,
    ) -> str:
        """Execute code or command in a secure environment (sandbox or host mode).

        Supported languages:
        - python: Execute Python code
        - nodejs: Execute Node.js code
        - command: Execute shell commands

        Storage paths (works in both modes):
        - /persistence: Private storage (persists across sessions, this chat only)
        - /shared: Shared storage (accessible by all chats)
        - Custom mounts: Per-chat volumes configured in settings

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
            language: Execution language: 'python', 'nodejs', or 'command'. Defaults to 'python'.
            timeout: Execution timeout in seconds (optional). For long-running tasks, use background=True instead.
            background: If True, run in background and return a process_id. Use ProcessTool to poll/kill.
        """
        self.chat_id = ctx.deps.chat_id
        self.sandbox_enabled = ctx.deps.sandbox_enabled
        self.workspace_root = ctx.deps.workspace_root
        if ctx.deps.custom_volumes and ctx.deps.custom_volumes != self.custom_volumes:
            self.set_custom_volumes(ctx.deps.custom_volumes)

        if not self.chat_id:
            return "Error: No chat context. Cannot determine execution session."

        denied_reason = self.is_tool_denied(ctx.deps, self.tool_name)
        if denied_reason:
            self.audit_operation(
                self.tool_name,
                "execute",
                "denied",
                language=language or "python",
                background=background,
                reason=denied_reason,
            )
            return f"Error: {denied_reason}"

        lang = (language or "python").strip().lower()
        if lang not in self._SUPPORTED_LANGUAGES:
            self.audit_operation(
                self.tool_name,
                "execute",
                "rejected",
                language=lang,
                background=background,
                reason="unsupported_language",
            )
            return (
                f"Error: Unsupported language '{language}'. "
                "Use 'python', 'nodejs', or 'command'."
            )

        if background:
            if not self.sandbox_enabled:
                return "Error: background=True requires sandbox mode."
            return self._execute_background(content, lang)

        if self.sandbox_enabled:
            return self._execute_in_sandbox(content, lang, timeout)
        return self._execute_on_host(content, lang, timeout)

    def _execute_background(self, content: str, language: str) -> str:
        """Start a background process and return its process_id."""
        try:
            proc_id = self.manager.start_background(
                session_id=self.chat_id,
                content=content,
                language=language,
            )
            self.audit_operation(
                self.tool_name,
                "background",
                "success",
                language=language,
                process_id=proc_id,
            )
            return (
                f"Background process started. process_id={proc_id}\n"
                f"Use ProcessTool to poll output: process_manage(process_id={proc_id!r}, action='poll')"
            )
        except Exception as e:
            logger.error(f"Background execution error: {e}")
            self.audit_operation(
                self.tool_name,
                "background",
                "error",
                language=language,
                error=str(e),
            )
            return f"Error starting background process: {e}"

    def _execute_in_sandbox(
        self,
        content: str,
        language: str,
        timeout: Optional[int] = None,
    ) -> str:
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
                self.audit_operation(
                    self.tool_name,
                    "execute",
                    "success",
                    mode="sandbox",
                    language=language,
                    timeout=timeout,
                    background=False,
                )
                return output
            else:
                logger.warning(f"Sandbox execution error: {result.error}")
                self.audit_operation(
                    self.tool_name,
                    "execute",
                    "error",
                    mode="sandbox",
                    language=language,
                    timeout=timeout,
                    background=False,
                    error=result.error,
                )
                return f"Execution Error: {result.error}"

        except Exception as e:
            logger.error(f"Sandbox tool error: {e}")
            self.audit_operation(
                self.tool_name,
                "execute",
                "error",
                mode="sandbox",
                language=language,
                timeout=timeout,
                background=False,
                error=str(e),
            )
            return f"Sandbox Error: {str(e)}"

    def _execute_on_host(
        self,
        content: str,
        language: str,
        timeout: Optional[int] = None,
    ) -> str:
        """Execute code directly on host machine, restricted to workspace."""
        if not self.workspace_root:
            return "[Error: workspace_root not configured for host execution]"

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
            self.audit_operation(
                self.tool_name,
                "execute",
                "success",
                mode="host",
                language=language,
                timeout=effective_timeout,
                background=False,
                returncode=result.returncode,
            )
            return output if output.strip() else "(no output)"

        except subprocess.TimeoutExpired:
            logger.warning(f"Host execution timed out after {effective_timeout}s")
            self.audit_operation(
                self.tool_name,
                "execute",
                "timeout",
                mode="host",
                language=language,
                timeout=effective_timeout,
                background=False,
            )
            return f"[Error: Command timed out after {effective_timeout} seconds]"
        except FileNotFoundError as e:
            logger.error(f"Host execution command not found: {e}")
            self.audit_operation(
                self.tool_name,
                "execute",
                "error",
                mode="host",
                language=language,
                timeout=effective_timeout,
                background=False,
                error=str(e),
            )
            return f"[Error: Command not found - {e}]"
        except Exception as e:
            logger.error(f"Host execution error: {e}")
            self.audit_operation(
                self.tool_name,
                "execute",
                "error",
                mode="host",
                language=language,
                timeout=effective_timeout,
                background=False,
                error=str(e),
            )
            return f"[Error: {str(e)}]"

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
