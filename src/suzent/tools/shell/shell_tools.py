"""Model-facing tools provided by :class:`ShellCapability`."""

from typing import Annotated, Optional

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import ToolGroup, ToolResult
from suzent.tools.shell.bash_tool import ShellCommandBackend
from suzent.tools.shell.process_tool import ShellProcessBackend


class RunCommandTool(ShellCommandBackend):
    """Run a command, yielding long-running processes for later checks."""

    name = "RunCommandTool"
    tool_name = "run_command"
    group = ToolGroup.SHELL
    display_name = "Run command"
    description = (
        "Run a shell command. Quick commands return complete output; commands still "
        "running after 10 seconds return an ID for check_command or stop_command."
    )
    deferrable = False
    session_guidance = (
        "Shell is for shell/system commands only. run_command yields an ID "
        "after 10 seconds if still running; use check_command/stop_command "
        "with that ID. Use start_command for known long-running "
        "processes. Never use Shell to read, search, or edit files; use the "
        "dedicated filesystem tools instead."
    )

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        content: Annotated[
            str,
            Field(description="Shell command to execute."),
        ],
        description: Annotated[
            str,
            Field(
                description="Concise active-voice description for approval and audit."
            ),
        ],
        timeout: Annotated[
            Optional[int],
            Field(
                ge=0,
                description=(
                    "Optional completion timeout in seconds. If omitted, return "
                    "a command ID after 10 seconds when still running."
                ),
            ),
        ] = None,
    ) -> ToolResult:
        return super().forward(
            ctx,
            content=content,
            description=description,
            timeout=timeout,
            background=False,
        )


class StartCommandTool(ShellCommandBackend):
    """Start a long-running command in the background."""

    name = "StartCommandTool"
    tool_name = "start_command"
    group = ToolGroup.SHELL
    display_name = "Start command"
    description = (
        "Start a long-running command in the background and return an ID for later "
        "status checks or cancellation. Completion automatically notifies the agent."
    )
    deferrable = False
    session_guidance = None

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        content: Annotated[
            str,
            Field(description="Shell command to start."),
        ],
        description: Annotated[
            str,
            Field(
                description="Concise active-voice description for approval and audit."
            ),
        ],
    ) -> ToolResult:
        return super().forward(
            ctx,
            content=content,
            description=description,
            timeout=None,
            background=True,
        )


class CheckCommandTool(ShellProcessBackend):
    """Read incremental output and status from a background command."""

    name = "CheckCommandTool"
    tool_name = "check_command"
    group = ToolGroup.SHELL
    display_name = "Check command"
    description = (
        "Read new output and the current status of a command started in the background."
    )
    requires_approval = False
    deferrable = False

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        command_id: Annotated[
            str,
            Field(description="Command ID returned by start_command or run_command."),
        ],
        offset: Annotated[
            int,
            Field(
                ge=0,
                description="Byte offset returned by the previous check; start at 0.",
            ),
        ] = 0,
    ) -> ToolResult:
        return super().forward(
            ctx,
            process_id=command_id,
            action="poll",
            offset=offset,
        )


class StopCommandTool(ShellProcessBackend):
    """Stop a background command and release its resources."""

    name = "StopCommandTool"
    tool_name = "stop_command"
    group = ToolGroup.SHELL
    display_name = "Stop command"
    description = "Stop a background command and clean up its process resources."
    deferrable = False

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        command_id: Annotated[
            str,
            Field(description="Command ID returned by start_command or run_command."),
        ],
    ) -> ToolResult:
        return super().forward(ctx, process_id=command_id, action="kill", offset=0)


SHELL_TOOL_CLASS_NAMES = (
    "RunCommandTool",
    "StartCommandTool",
    "CheckCommandTool",
    "StopCommandTool",
)

SHELL_RUNTIME_NAMES = frozenset(
    {"run_command", "start_command", "check_command", "stop_command"}
)
