"""Hand finished files to the person in this conversation, wherever they are talking from."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any, Coroutine, Optional

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.logger import get_logger
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult
from suzent.tools.filesystem.file_tool_utils import get_or_create_path_resolver

logger = get_logger(__name__)

MAX_FILES = 10
MB = 1024 * 1024
SEND_TIMEOUT_SECONDS = 120


async def _on_channel_loop(
    coroutine: Coroutine[Any, Any, bool], loop: Optional[asyncio.AbstractEventLoop]
) -> bool:
    """Run a channel call on the loop its client lives on."""
    if loop is None or loop is asyncio.get_running_loop():
        return await asyncio.wait_for(coroutine, SEND_TIMEOUT_SECONDS)
    future = asyncio.run_coroutine_threadsafe(coroutine, loop)
    return await asyncio.wait_for(asyncio.wrap_future(future), SEND_TIMEOUT_SECONDS)


class SendFileTool(Tool):
    """Deliver finished files to the user in this conversation: through the chat app they wrote from, or as attachments on the desktop and phone."""

    name = "SendFileTool"
    tool_name = "send_file"
    group = ToolGroup.INTERACTION
    builtin = True
    requires_approval = False
    session_guidance = (
        "When the user should receive a finished file (a document, image, video, audio "
        "or archive), call send_file instead of only naming its path: it reaches them in "
        "the chat app they wrote from, or as an attachment on the desktop and phone. Send "
        "deliverables, not drafts or intermediate files. To send to someone else, use "
        "social_message."
    )
    guidance_priority = 60

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        paths: Annotated[
            list[str],
            Field(
                description="Files in the workspace to deliver, up to 10.",
                min_length=1,
                max_length=MAX_FILES,
            ),
        ],
        caption: Annotated[
            Optional[str],
            Field(description="Optional short note sent with the first file."),
        ] = None,
    ) -> ToolResult:
        resolver = get_or_create_path_resolver(ctx.deps)
        files: list[Path] = []
        for raw in dict.fromkeys(paths):
            try:
                path = resolver.resolve(raw)
            except ValueError as exc:
                return ToolResult.error_result(
                    ToolErrorCode.PERMISSION_DENIED,
                    f"{raw} is outside the folders this conversation may read: {exc}",
                )
            if not path.is_file():
                return ToolResult.error_result(
                    ToolErrorCode.FILE_NOT_FOUND, f"{raw} is not an existing file."
                )
            files.append(path)

        # Virtual paths, because the desktop and phone load attachments back through the resolver.
        saved_paths = [resolver.to_virtual_path(path) or str(path) for path in files]
        social = ctx.deps.social_context or {}
        platform = social.get("platform")
        target = social.get("target_id")
        if not (platform and target):
            return ToolResult.success_result(
                f"Shared {len(files)} file(s) in this conversation. They appear as "
                "attachments on the desktop and on paired phones.",
                metadata={"saved_paths": saved_paths, "delivered_paths": saved_paths},
            )
        return await self._send_to_channel(
            ctx.deps, platform, target, files, caption, saved_paths
        )

    async def _send_to_channel(
        self,
        deps: AgentDeps,
        platform: str,
        target: str,
        files: list[Path],
        caption: Optional[str],
        saved_paths: list[str],
    ) -> ToolResult:
        manager = deps.channel_manager
        loop = deps.event_loop
        if manager is None:
            from suzent.channels.utils import get_channel_manager

            manager = get_channel_manager()
        if manager is None:
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                "Chat apps are not connected, so the file could not be sent.",
                metadata={"saved_paths": saved_paths, "channel": platform},
            )
        channel = manager.channels.get(platform)
        if channel is not None and not channel.supports_files:
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"{platform} can't receive files from Suzent yet. Tell the user where "
                "the file is saved on their computer instead.",
                metadata={"saved_paths": saved_paths, "channel": platform},
            )

        limit = channel.max_file_bytes if channel is not None else None
        delivered: list[str] = []
        failed: dict[str, str] = {}
        for path, shown in zip(files, saved_paths):
            if limit is not None and path.stat().st_size > limit:
                failed[shown] = f"larger than {platform}'s {limit // MB} MB limit"
                continue
            note = caption if not delivered else None
            try:
                sent = await _on_channel_loop(
                    manager.send_file(platform, target, str(path), note), loop
                )
            except TimeoutError:
                sent = False
                failed[shown] = "timed out"
            except Exception as exc:
                logger.warning(
                    "Sending a file to {} failed: {}", platform, type(exc).__name__
                )
                sent = False
                failed[shown] = "the chat app rejected it"
            if sent:
                delivered.append(shown)
            else:
                failed.setdefault(shown, "the chat app rejected it")

        metadata = {
            "saved_paths": saved_paths,
            "delivered_paths": delivered,
            "channel": platform,
            "failed": failed,
        }
        if not delivered:
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"No file reached {platform}: "
                + "; ".join(f"{Path(p).name}: {why}" for p, why in failed.items()),
                metadata=metadata,
            )
        message = f"Sent {len(delivered)} file(s) to {platform}."
        if failed:
            message += " Not sent: " + "; ".join(
                f"{Path(p).name} ({why})" for p, why in failed.items()
            )
        return ToolResult.success_result(message, metadata=metadata)
