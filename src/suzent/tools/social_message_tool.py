"""
Social message tool for sending progress updates to social channels.

Allows the agent to proactively send intermediate messages to the user's
social platform (Telegram, Slack, Discord, Feishu) while working on a task.
"""

import asyncio
from typing import Optional

from pydantic_ai import RunContext
from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool

from suzent.logger import get_logger

logger = get_logger(__name__)

# Platform character limits
PLATFORM_CHAR_LIMITS = {
    "telegram": 4096,
    "slack": 40000,
    "discord": 2000,
    "feishu": 30000,
}


class SocialMessageTool(Tool):
    name = "SocialMessageTool"
    tool_name = "social_message"
    requires_approval = True

    def __init__(self):
        super().__init__()
        self._channel_manager = None
        self._event_loop = None
        self._default_platform: Optional[str] = None
        self._default_target: Optional[str] = None

    def _list_contacts(self, platform_filter: Optional[str] = None) -> str:
        """Return available channels and known contacts from recent social chats."""
        lines = []

        # Resolve effective filter: explicit param > default from social mode
        platform = platform_filter or self._default_platform

        configured = (
            list(self._channel_manager.channels.keys()) if self._channel_manager else []
        )

        if platform:
            if platform not in configured and configured:
                lines.append(
                    f"Channel '{platform}' is not configured. Available: {', '.join(configured)}"
                )
                return "\n".join(lines)
            lines.append(f"Channel: {platform}")
        else:
            lines.append(
                f"Available channels: {', '.join(configured) if configured else 'none'}"
            )

        # Query social chats with full config to get target_id
        try:
            from suzent.database import get_database
            from sqlmodel import select

            db = get_database()
            with db._session() as session:
                from suzent.database import ChatModel

                stmt = (
                    select(ChatModel)
                    .where(ChatModel.id.startswith("social-"))
                    .order_by(ChatModel.updated_at.desc())
                    .limit(50)
                )
                chats = session.exec(stmt).all()

            contacts = []
            for chat in chats:
                cfg = chat.config or {}
                chat_platform = cfg.get("platform")
                if not chat_platform:
                    continue
                if platform and chat_platform != platform:
                    continue

                target = cfg.get("target_id") or cfg.get("sender_id", "?")
                entry = f"  - {chat.title} | recipient={target}"
                if not platform:
                    entry = f"  - {chat.title} | channel={chat_platform}, recipient={target}"
                contacts.append(entry)

                if len(contacts) >= 10:
                    break

            if contacts:
                lines.append("Known contacts:")
                lines.extend(contacts)
            else:
                scope = f" on {platform}" if platform else ""
                lines.append(f"No previous social conversations found{scope}.")
        except Exception as e:
            lines.append(f"Could not query contacts: {e}")

        return "\n".join(lines)

    def forward(
        self,
        ctx: RunContext[AgentDeps],
        message: Optional[str] = None,
        channel: Optional[str] = None,
        recipient: Optional[str] = None,
        list_contacts: Optional[bool] = None,
    ) -> str:
        """Send a message to a social platform, or list known contacts.

        Call with list_contacts=true to discover available channels and
        recipient IDs before sending a message.

        Args:
            ctx: The pydantic-ai run context with agent dependencies.
            message: The text message to send. Ignored when list_contacts is true.
            channel: Platform name (telegram/slack/discord/feishu). Defaults to current social channel if in social mode.
            recipient: Recipient/chat ID. Defaults to current conversation partner if in social mode.
            list_contacts: Set to true to list available channels and known contacts instead of sending a message.
        """
        # Extract social context from deps
        deps = ctx.deps
        self._channel_manager = deps.channel_manager
        self._event_loop = deps.event_loop
        self._default_platform = deps.social_context.get("platform")
        self._default_target = deps.social_context.get("target_id")

        if not self._channel_manager:
            from suzent.core.social_brain import get_active_social_brain
            brain = get_active_social_brain()
            if brain:
                self._channel_manager = brain.channel_manager
                try:
                    self._event_loop = asyncio.get_running_loop()
                except RuntimeError:
                    self._event_loop = None

        if list_contacts:
            return self._list_contacts(platform_filter=channel)

        if not message:
            return "Error: 'message' is required when not using list_contacts=true."

        platform = channel or self._default_platform
        target = recipient or self._default_target

        if not platform:
            return "Error: No channel specified and no default set. Use list_contacts=true to see available options."

        if not target:
            return "Error: No recipient specified and no default set. Use list_contacts=true to see known contacts."

        if not self._channel_manager:
            return "Error: Social messaging is not configured. No channel manager available."

        if not self._event_loop:
            return "Error: Event loop not available for async message dispatch."

        # Enforce platform character limit
        char_limit = PLATFORM_CHAR_LIMITS.get(platform, 4096)
        if len(message) > char_limit:
            message = message[: char_limit - 3] + "..."
            logger.warning(f"Message truncated to {char_limit} chars for {platform}")

        # Sync-to-async bridge: agent tools run in a background thread
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._channel_manager.send_message(platform, target, message),
                self._event_loop,
            )
            success = future.result(timeout=30)

            if success:
                return f"Message sent to {platform}:{target}"
            else:
                return f"Failed to send message to {platform}:{target}"

        except TimeoutError:
            logger.error(f"Timeout sending message to {platform}:{target}")
            return f"Error: Timeout sending message to {platform}:{target}"
        except Exception as e:
            logger.error(f"Error sending social message: {e}")
            return f"Error sending message: {e}"
