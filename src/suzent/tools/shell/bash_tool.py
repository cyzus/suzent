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
from pydantic_ai import ApprovalRequired, RunContext
from suzent.core.agent_deps import AgentDeps
from suzent.tools.filesystem.file_tool_utils import get_or_create_path_resolver
from suzent.tools.shell.permissions import CommandDecision, evaluate_command_policy
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

from suzent.logger import get_logger

logger = get_logger(__name__)

_MAX_OUTPUT_CHARS = 30_000


def _truncate_output(text: str) -> str:
    """Truncate output to _MAX_OUTPUT_CHARS, appending a line-count summary."""
    if not text or len(text) <= _MAX_OUTPUT_CHARS:
        return text
    truncated = text[:_MAX_OUTPUT_CHARS]
    remaining_lines = text[_MAX_OUTPUT_CHARS:].count("\n") + 1
    return truncated + f"\n... [{remaining_lines} lines truncated]"


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
    requires_approval = False
    session_guidance = (
        "BashTool is for shell/system commands ONLY. "
        "NEVER use bash to read, search, or edit files (no cat, head, tail, grep, find, sed, awk). "
        "Use read_file, grep_search, glob_search, edit_file, write_file instead."
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

    def _audit_execution(
        self, status: str, description: Optional[str] = None, **kwargs
    ):
        if description:
            kwargs["description"] = description
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
        description: Annotated[
            str,
            Field(
                description=(
                    "Required concise description of what this command does in active voice "
                    "(e.g. 'List Python files in src/', 'Run test suite'). "
                    "Used for approval UX and audit logging."
                ),
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
        """Executes a shell command or code and returns its output.

        The working directory persists between commands within a session.

        Supported languages:
        - command: Shell commands (bash on Linux/Mac, PowerShell on Windows)
        - python: Execute Python code
        - nodejs: Execute Node.js code

        Output is capped at 30,000 characters. stdout and stderr are returned separately.

        Storage paths (host mode env vars):
        - WORKSPACE_ROOT, PERSISTENCE_PATH, SHARED_PATH, CHAT_ID, MOUNT_* for custom volumes

        Args:
            ctx: The pydantic-ai run context with agent dependencies.
            content: The code or shell command to execute.
            description: Short description of what the command does (for audit log).
            language: Execution language. Defaults to 'command'.
            timeout: Execution timeout in seconds. For long-running tasks use background=True.
            background: If True, run in background and return a process_id.
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

        from suzent.config import CONFIG

        policy_map = {}
        if hasattr(CONFIG, "permission_policies"):
            policy_map = dict(getattr(CONFIG, "permission_policies") or {})
        if hasattr(ctx.deps, "tool_permission_policies"):
            policy_map = dict(getattr(ctx.deps, "tool_permission_policies") or {})

        tool_policy = policy_map.get(self.tool_name) or policy_map.get(self.name) or {}
        if not isinstance(tool_policy, dict):
            tool_policy = {}

        denied_reason = self.is_tool_denied(ctx.deps, self.tool_name)
        if denied_reason:
            self.audit_operation(
                self.tool_name,
                "execute",
                "denied",
                language=language,
                background=background,
                reason=denied_reason,
                description=description,
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
                description=description,
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

        policy_enabled = bool(tool_policy.get("enabled", False))
        mode_value = str(tool_policy.get("mode", "full_approval"))
        default_action = str(tool_policy.get("default_action", "ask"))
        raw_rules = tool_policy.get("command_rules", [])

        if lang == "command":
            resolver = get_or_create_path_resolver(ctx.deps)
            baseline_eval = evaluate_command_policy(
                command_text=content,
                resolver=resolver,
                mode_value="accept_edits",
                raw_rules=[],
                default_action="ask",
            )

            baseline_hard_reasons = (
                "Command blocked by high-risk shell semantics",
                "Path denied by policy",
                "Dangerous delete target blocked",
            )
            if (
                baseline_eval.decision == CommandDecision.DENY
                and baseline_eval.reason.startswith(baseline_hard_reasons)
            ):
                self.audit_operation(
                    self.tool_name,
                    "policy",
                    "deny",
                    language=lang,
                    mode="baseline",
                    reason=baseline_eval.reason,
                    description=description,
                    command_class=baseline_eval.command_class.value,
                )
                return self._error_result(
                    ToolErrorCode.PERMISSION_DENIED,
                    f"Command blocked by baseline guardrails: {baseline_eval.reason}",
                    mode="unknown",
                    language=lang,
                    timeout=timeout,
                    background=background,
                    policy_decision="deny",
                    policy_reason=baseline_eval.reason,
                    command_class=baseline_eval.command_class.value,
                )

            baseline_ask_reasons = (
                "Command requires approval due to shell chaining semantics",
                "Git commands require approval",
            )
            if (
                baseline_eval.decision == CommandDecision.ASK
                and baseline_eval.reason.startswith(baseline_ask_reasons)
            ):
                self.audit_operation(
                    self.tool_name,
                    "policy",
                    "ask",
                    language=lang,
                    mode="baseline",
                    reason=baseline_eval.reason,
                    description=description,
                    command_class=baseline_eval.command_class.value,
                )
                if not bool(getattr(ctx, "tool_call_approved", False)):
                    raise ApprovalRequired(
                        metadata={
                            "reason": baseline_eval.reason,
                            "mode": "baseline",
                            "command_class": baseline_eval.command_class.value,
                            "description": description,
                        }
                    )

        if policy_enabled and lang == "command":
            policy_eval = evaluate_command_policy(
                command_text=content,
                resolver=resolver,
                mode_value=mode_value,
                raw_rules=raw_rules,
                default_action=default_action,
            )

            self.audit_operation(
                self.tool_name,
                "policy",
                policy_eval.decision.value,
                language=lang,
                mode=mode_value,
                reason=policy_eval.reason,
                description=description,
                command_class=policy_eval.command_class.value,
            )

            if policy_eval.decision == CommandDecision.DENY:
                return self._error_result(
                    ToolErrorCode.PERMISSION_DENIED,
                    f"Command blocked by bash policy: {policy_eval.reason}",
                    mode="unknown",
                    language=lang,
                    timeout=timeout,
                    background=background,
                    policy_decision=policy_eval.decision.value,
                    policy_reason=policy_eval.reason,
                    command_class=policy_eval.command_class.value,
                )

            if policy_eval.decision == CommandDecision.ASK:
                if not bool(getattr(ctx, "tool_call_approved", False)):
                    raise ApprovalRequired(
                        metadata={
                            "reason": policy_eval.reason,
                            "mode": mode_value,
                            "command_class": policy_eval.command_class.value,
                            "description": description or "",
                        }
                    )

        if background:
            if self.sandbox_enabled:
                return self._execute_background(content, lang, description=description)
            return self._execute_background_on_host(
                content, lang, description=description
            )

        if self.sandbox_enabled:
            return self._execute_in_sandbox(
                content, lang, timeout, description=description
            )
        return self._execute_on_host(content, lang, timeout, description=description)

    def _execute_background(
        self, content: str, language: str, description: Optional[str] = None
    ) -> ToolResult:
        """Start a background process and return its process_id."""
        try:
            proc_id = self.manager.start_background(
                session_id=self.chat_id,
                content=content,
                language=language,
            )
            self._audit_execution(
                "background",
                description=description,
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
                description=description,
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
        description: Optional[str] = None,
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
                output = (
                    _truncate_output(result.output) if result.output else "(no output)"
                )
                logger.info(
                    f"Sandbox execution successful [{language}] for chat {self.chat_id}"
                )
                self._audit_execution(
                    "success",
                    description=description,
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
                    description=description,
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

    def _execute_background_on_host(
        self,
        content: str,
        language: str,
        description: Optional[str] = None,
    ) -> ToolResult:
        """Start a background process on the host and return its process_id."""
        from suzent.tools.shell.host_process_registry import HostProcessRegistry

        if not self.workspace_root:
            return self._error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "workspace_root not configured for host execution",
                mode="host",
                language=language,
                timeout=None,
                background=True,
            )

        cmd = self._build_cmd(content, language)
        working_dir = self._resolve_working_dir()
        env = self._get_host_env()

        try:
            registry = HostProcessRegistry()
            process_id = registry.start(
                chat_id=self.chat_id,
                cmd=cmd,
                cwd=str(working_dir),
                env=env,
            )
            self._audit_execution(
                "background",
                description=description,
                mode="host",
                language=language,
                process_id=process_id,
            )
            return self._success_result(
                "Background process started. Use process_manage to poll output.",
                mode="host",
                language=language,
                timeout=None,
                background=True,
                process_id=process_id,
            )
        except Exception as e:
            logger.error(f"Host background execution error: {e}")
            return self._error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Error starting background process: {e}",
                mode="host",
                language=language,
                timeout=None,
                background=True,
            )

    def _build_cmd(self, content: str, language: str) -> list[str]:
        """Build the command list for the given language."""
        if language == "python":
            return ["python", "-c", content]
        elif language == "nodejs":
            return ["node", "-e", content]
        elif language == "command" and os.name == "nt":
            utf8_preamble = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            return ["powershell", "-NoProfile", "-Command", utf8_preamble + content]
        else:
            return ["bash", "-c", content]

    def _resolve_working_dir(self) -> Path:
        """Resolve and create the working directory for host execution."""
        from suzent.config import CONFIG

        if self.cwd:
            working_dir = Path(self.cwd).resolve()
        else:
            sandbox_data_path = Path(CONFIG.sandbox_data_path).resolve()
            working_dir = sandbox_data_path / "sessions" / self.chat_id
        working_dir.mkdir(parents=True, exist_ok=True)
        return working_dir

    def _execute_on_host(
        self,
        content: str,
        language: str,
        timeout: Optional[int] = None,
        description: Optional[str] = None,
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

        cmd = self._build_cmd(content, language)
        working_dir = self._resolve_working_dir()
        effective_timeout = timeout or 120

        try:
            result = subprocess.run(
                cmd,
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=effective_timeout,
                env=self._get_host_env(),
            )

            stdout = _truncate_output(result.stdout)
            stderr = _truncate_output(result.stderr)

            parts = []
            if stdout.strip():
                parts.append(stdout)
            if stderr.strip():
                parts.append(f"[stderr]\n{stderr}")
            if result.returncode != 0:
                parts.append(f"[exit code: {result.returncode}]")

            body = "\n".join(parts) if parts else "(no output)"
            output = f"[cwd: {working_dir}]\n{body}"

            logger.info(
                f"Host execution successful [{language}] for chat {self.chat_id}"
            )
            self._audit_execution(
                "success",
                description=description,
                mode="host",
                language=language,
                timeout=effective_timeout,
                background=False,
                returncode=result.returncode,
            )
            return self._success_result(
                output,
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
