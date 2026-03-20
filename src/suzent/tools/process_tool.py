"""
ProcessTool
===========

Interact with background processes started by BashTool (background=True).

Actions:
- poll   : Read new output since last offset. Returns output, new offset, done status.
- status : Check if the process is still running and its exit code.
- kill   : Send SIGTERM to stop the process.

Usage (agent perspective):
    # Start a long-running process
    process_id = bash_execute(content="npm install", language="command", background=True)

    # Poll for output
    process_manage(process_id="abc123", action="poll")

    # Kill if needed
    process_manage(process_id="abc123", action="kill")
"""

from __future__ import annotations

from typing import Optional

from pydantic_ai import RunContext
from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool
from suzent.logger import get_logger

logger = get_logger(__name__)


class ProcessTool(Tool):
    """
    Manage background processes started with BashTool(background=True).

    Actions:
    - poll:   Read new output since last offset.
              Returns: output text, next_offset (pass back on next poll),
              done (bool), exit_code (int or null).
    - status: Check if the process is still running.
    - kill:   Stop the process with SIGTERM.
    """

    name = "ProcessTool"
    tool_name = "process_manage"
    requires_approval = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._manager = None
        self.chat_id: Optional[str] = None

    @property
    def manager(self):
        if self._manager is None:
            from suzent.sandbox import SandboxManager

            self._manager = SandboxManager()
        return self._manager

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        process_id: str,
        action: str,
        offset: int = 0,
    ) -> str:
        """Manage a background process.

        Args:
            process_id: The ID returned by bash_execute when background=True.
            action: One of "poll", "status", or "kill".
            offset: For "poll" only — byte offset from previous poll response.
                    Start at 0, then pass the returned next_offset on each call.
        """
        self.chat_id = ctx.deps.chat_id

        if not self.chat_id:
            return "Error: No chat context."

        if not ctx.deps.sandbox_enabled:
            return "Error: ProcessTool requires sandbox mode to be enabled."

        action = action.lower().strip()

        if action == "poll":
            return self._poll(process_id, offset)
        elif action == "status":
            return self._status(process_id)
        elif action == "kill":
            return self._kill(process_id)
        else:
            return f"Error: Unknown action '{action}'. Use 'poll', 'status', or 'kill'."

    def _poll(self, process_id: str, offset: int) -> str:
        try:
            result = self.manager.poll_process(self.chat_id, process_id, offset)
            output = result.get("output", "")
            next_offset = result.get("offset", offset)
            done = result.get("done", False)
            exit_code = result.get("exit_code")

            lines = []
            if output:
                lines.append(output.rstrip())
            lines.append(
                f"[next_offset={next_offset} | "
                f"{'done, exit_code=' + str(exit_code) if done else 'still running'}]"
            )
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"ProcessTool poll error: {e}")
            return f"Error polling process {process_id}: {e}"

    def _status(self, process_id: str) -> str:
        try:
            result = self.manager.poll_process(self.chat_id, process_id, offset=0)
            done = result.get("done", False)
            exit_code = result.get("exit_code")
            if done:
                return f"Process {process_id} finished with exit code {exit_code}."
            return f"Process {process_id} is still running."
        except Exception as e:
            return f"Error getting status for {process_id}: {e}"

    def _kill(self, process_id: str) -> str:
        try:
            ok = self.manager.kill_process(self.chat_id, process_id)
            return (
                f"Process {process_id} terminated."
                if ok
                else f"Could not kill {process_id} (already done or not found)."
            )
        except Exception as e:
            return f"Error killing process {process_id}: {e}"
