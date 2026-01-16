"""
Sandbox Tool for Agent
======================

Provides isolated code execution within agent conversations.
Each chat session gets its own sandbox with persistent storage.
"""

from __future__ import annotations

from typing import Optional
from smolagents.tools import Tool

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
    description = """Execute code in a secure, isolated sandbox environment.

Supported languages:
- python: Execute Python code
- nodejs: Execute Node.js code
- command: Execute shell commands

Storage paths inside sandbox:
- /persistence: Private storage (persists across sessions, this chat only)
- /shared: Shared storage (accessible by all chats)
- Custom mounts: Per-chat volumes configured in settings

Returns the execution output or error message."""

    inputs = {
        "content": {
            "type": "string",
            "description": "The code or shell command to execute",
        },
        "language": {
            "type": "string",
            "description": "Execution language: 'python', 'nodejs', or 'command'",
            "default": "python",
            "nullable": True,
        },
        "timeout": {
            "type": "integer",
            "description": "Execution timeout in seconds (optional)",
            "nullable": True,
        },
    }
    output_type = "string"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._manager = None
        self.chat_id: Optional[str] = None
        self.custom_volumes: Optional[list] = None

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
        content: str,
        language: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> str:
        """
        Execute code or command in the sandbox.

        Args:
            content: Code or command to execute
            language: Execution language (python, nodejs, command)
            timeout: Execution timeout in seconds

        Returns:
            Output from execution, or error message
        """
        if not self.chat_id:
            return "Error: No chat context. Cannot determine sandbox session."

        # Default to Python if not specified
        lang = language or "python"

        try:
            # Manager is now synchronous - no async needed
            result = self.manager.execute(
                session_id=self.chat_id, content=content, language=lang, timeout=timeout
            )

            if result.success:
                output = result.output or "(no output)"
                logger.info(
                    f"Sandbox execution successful [{lang}] for chat {self.chat_id}"
                )
                return output
            else:
                logger.warning(f"Sandbox execution error: {result.error}")
                return f"Execution Error: {result.error}"

        except Exception as e:
            logger.error(f"Sandbox tool error: {e}")
            return f"Sandbox Error: {str(e)}"
