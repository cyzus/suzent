"""Desktop tool: one agent-desktop command per call, on the host only."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.logger import get_logger
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult
from suzent.tools.desktop import runner as desktop_runner
from suzent.tools.desktop.catalog import DesktopCommand, DesktopOptions, prepare_call
from suzent.tools.desktop.runner import (
    DesktopBinaryError,
    DesktopTimeout,
    parse_envelope,
    render_envelope,
)

logger = get_logger(__name__)

_COMMAND_HELP = (
    "agent-desktop command. Observe with snapshot, find, get, or is, then act "
    "on a qualified ref (@snapshot:eN). Read-only commands are allowed; clicks, "
    "typing, launch, and other changes ask for approval. "
    "Before the first use, call skills with subcommand get and skill desktop, "
    "then skill platform. trace and cursor-overlay are not wrapped."
)


class DesktopTool(Tool):
    """Read and operate native desktop apps through agent-desktop."""

    name = "DesktopTool"
    tool_name = "desktop"
    display_name = "Desktop"
    description = (
        "Read and operate native apps on this computer. Observation runs on its "
        "own; clicks, typing, and other changes ask first. Always uses the host "
        "desktop, never the Docker sandbox."
    )
    group = ToolGroup.DESKTOP
    requires_approval = True
    deferrable = True
    guidance_priority = 40
    session_guidance = (
        "Desktop control uses the desktop tool and the host's agent-desktop CLI, "
        "never the shell and never the Docker sandbox. Load the suzent-desktop "
        "skill first. Snapshot or find, act on a qualified ref, then snapshot "
        "again. Leave headed off unless a command reports that physical input is "
        "required. Retry an action only when the error says retry is safe."
    )

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        command: Annotated[DesktopCommand, Field(description=_COMMAND_HELP)],
        options: Annotated[
            DesktopOptions | None,
            Field(
                description=(
                    "Command flags. Common keys: app, window_id, ref, text, value, "
                    "timeout_ms. snapshot also takes interactive_only, compact, "
                    "skeleton, root, and surface. Batch entries are {command, args} "
                    "in the CLI's underscore form. headed is a separate argument."
                )
            ),
        ] = None,
        headed: Annotated[
            bool,
            Field(
                description=(
                    "Pass --headed. Default false: accessibility actions do not move "
                    "the pointer or steal focus. Set true only when the command "
                    "needs physical input."
                )
            ),
        ] = False,
        session: Annotated[
            str | None,
            Field(
                description="agent-desktop --session id. Omit to use the default namespace."
            ),
        ] = None,
    ) -> ToolResult:
        """Drive a native desktop app through the agent-desktop CLI.

        The loop is snapshot (or find), act on a ref from that snapshot, then
        snapshot again. Refs look like @s8f3k2p9:e8 and die when the UI changes;
        a bare @eN is invalid. On STALE_REF or AMBIGUOUS_TARGET, take a new
        snapshot. ok true does not prove the app saved the change: read
        delivery and retry, and only repeat an action when retry is safe.

        This always runs on the host computer. The chat sandbox has no display
        and is not used. Suzent does not install agent-desktop; the 1.0.x CLI
        must already be on PATH or in SUZENT_AGENT_DESKTOP_BIN.
        """
        try:
            prepared = prepare_call(command, options, headed=headed, session=session)
        except ValueError as exc:
            return ToolResult.error_result(ToolErrorCode.INVALID_ARGUMENT, str(exc))

        # Shell commands may be diverted into the chat sandbox. Desktop commands
        # stay in this process because that sandbox has no display.
        logger.debug(
            "Desktop {} on the host (chat sandbox enabled: {})",
            prepared.command,
            bool(getattr(ctx.deps, "sandbox_enabled", False)),
        )

        try:
            binary = desktop_runner.resolve_binary()
        except DesktopBinaryError as exc:
            return ToolResult.error_result(ToolErrorCode.EXECUTION_FAILED, str(exc))

        unsupported = await desktop_runner.ensure_supported_binary(binary)
        if unsupported:
            return ToolResult.error_result(ToolErrorCode.EXECUTION_FAILED, unsupported)

        try:
            _code, stdout, stderr = await desktop_runner.run_cli(
                binary, prepared.argv, timeout=prepared.timeout_seconds
            )
        except DesktopTimeout as exc:
            Tool.audit_operation("desktop", prepared.command, "timeout")
            return ToolResult.error_result(ToolErrorCode.TIMEOUT, str(exc))
        except DesktopBinaryError as exc:
            return ToolResult.error_result(ToolErrorCode.EXECUTION_FAILED, str(exc))
        except OSError as exc:
            logger.error("Failed to start agent-desktop: {}", exc)
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Could not start agent-desktop: {exc}",
            )
        except ValueError as exc:
            return ToolResult.error_result(ToolErrorCode.EXECUTION_FAILED, str(exc))

        try:
            envelope = parse_envelope(stdout)
        except ValueError as exc:
            detail = stderr.strip()
            message = str(exc)
            if detail:
                message = f"{message}\nstderr: {detail[:500]}"
            Tool.audit_operation("desktop", prepared.command, "invalid_output")
            return ToolResult.error_result(ToolErrorCode.EXECUTION_FAILED, message)

        rendered = render_envelope(envelope)
        outcome = "ok" if rendered.ok else str(rendered.error_code or "error")
        Tool.audit_operation("desktop", prepared.command, outcome)
        if rendered.ok:
            return ToolResult.success_result(
                rendered.message, metadata=rendered.metadata
            )
        return ToolResult.error_result(
            _tool_error_code(rendered.error_code or "INTERNAL"),
            rendered.message,
            metadata=rendered.metadata,
        )


def _tool_error_code(agent_code: str) -> ToolErrorCode:
    match agent_code:
        case "PERM_DENIED":
            return ToolErrorCode.PERMISSION_DENIED
        case "TIMEOUT":
            return ToolErrorCode.TIMEOUT
        case "INVALID_ARGS":
            return ToolErrorCode.INVALID_ARGUMENT
        case (
            "ELEMENT_NOT_FOUND"
            | "APP_NOT_FOUND"
            | "WINDOW_NOT_FOUND"
            | "NOTIFICATION_NOT_FOUND"
            | "SNAPSHOT_NOT_FOUND"
        ):
            return ToolErrorCode.NOT_FOUND
        case _:
            return ToolErrorCode.EXECUTION_FAILED
