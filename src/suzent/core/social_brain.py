"""
Social Brain: The bridge between Social Channels and the Suzent Agent.
"""

import asyncio
from typing import Optional
from suzent.logger import get_logger
from suzent.channels.manager import ChannelManager
from suzent.channels.base import UnifiedMessage
from suzent.config import CONFIG
from suzent.database import get_database

logger = get_logger(__name__)


class SocialBrain:
    """
    Consumer that processes messages from the ChannelManager queue
    and dispatches them to the AI Agent.
    """

    def __init__(
        self,
        channel_manager: ChannelManager,
        allowed_users: list = None,
        platform_allowlists: dict = None,
        model: str = None,
        memory_enabled: bool = True,
        tools: list = None,
        mcp_enabled: dict = None,
    ):
        self.channel_manager = channel_manager
        self.allowed_users = set(allowed_users) if allowed_users else set()
        self.platform_allowlists = (
            {k: set(v) for k, v in platform_allowlists.items()}
            if platform_allowlists
            else {}
        )
        self.model = model
        self.memory_enabled = memory_enabled
        self.tools = tools
        self.mcp_enabled = mcp_enabled
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def update_model(self, model: str):
        """Update the model used for social interactions."""
        self.model = model

    async def start(self):
        """Start the processing loop."""
        self._running = True
        self._task = asyncio.create_task(self._process_queue())
        logger.info("SocialBrain started.")

    async def stop(self):
        """Stop the processing loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SocialBrain stopped.")

    async def _process_queue(self):
        """Main loop consuming messages."""
        while self._running:
            try:
                # Wait for message
                message: UnifiedMessage = await self.channel_manager.message_queue.get()

                # Process in background task to not block queue
                asyncio.create_task(self._handle_message(message))

                self.channel_manager.message_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in SocialBrain loop: {e}")
                await asyncio.sleep(1)

    def _is_authorized(self, message: UnifiedMessage) -> bool:
        """Check if a message sender is authorized."""
        # No restrictions if both lists are empty
        platform_allowed = self.platform_allowlists.get(message.platform)
        if not self.allowed_users and not platform_allowed:
            return True

        # Check if sender is in either global or platform-specific allowlist
        identifiers = {message.sender_id, message.sender_name}

        if self.allowed_users and identifiers & self.allowed_users:
            return True

        if platform_allowed and identifiers & platform_allowed:
            return True

        return False

    async def _handle_message(self, message: UnifiedMessage):
        """
        Handle a single message using ChatProcessor.
        """
        # 1. Access Control
        if not self._is_authorized(message):
            logger.warning(
                f"Unauthorized social message from: {message.sender_name} ({message.sender_id}) on {message.platform}"
            )
            await self.channel_manager.send_message(
                message.platform,
                message.sender_id,
                "⛔ Access Denied. You are not authorized to use this bot.",
            )
            return

        try:
            # 2. Resolve Chat ID
            social_chat_id = f"social-{message.platform}-{message.sender_id}"
            self._ensure_chat_exists(social_chat_id, message)

            logger.info(
                f"Processing social message for {social_chat_id}: {message.content}"
            )

            # 3. Setup Processor
            from suzent.core.chat_processor import ChatProcessor

            processor = ChatProcessor()

            # Prepare config overrides
            config_override = {
                "model": self.model,
                "tools": self.tools,
                "mcp_enabled": self.mcp_enabled,
            }

            # 4. Process and Reply
            # We iterate over the stream to find errors or forward chunks if we supported streaming typing.
            # But social channels usually prefer a full message currently, or optimized updates.
            # The current implementation accumulated the full response and sent it once.

            full_response = ""
            async for chunk in processor.process_turn(
                chat_id=social_chat_id,
                user_id=CONFIG.user_id,
                message_content=message.content,
                files=message.attachments,  # ChatProcessor handles dicts
                config_override=config_override,
            ):
                # Accumulate response from chunks
                if chunk.startswith("data: "):
                    try:
                        import json

                        data = json.loads(chunk[6:].strip())
                        evt = data.get("type")
                        content = data.get("data")

                        if evt == "final_answer":
                            full_response = content
                        elif evt == "error":
                            logger.error(f"Agent error: {content}")
                            await self.channel_manager.send_message(
                                message.platform,
                                message.sender_id,
                                f"⚠️ Error: {content}",
                            )
                            return
                    except Exception:
                        pass

            # Send Final Response
            # We need to target the correct ID.
            target_id = message.get_chat_id().split(":", 1)[1]
            if full_response.strip():
                await self.channel_manager.send_message(
                    message.platform, target_id, full_response
                )

        except Exception as e:
            logger.error(f"Failed to handle social message: {e}")

    def _ensure_chat_exists(self, chat_id: str, message: UnifiedMessage):
        """Ensure a record exists in the DB for this chat."""
        db = get_database()
        chat = db.get_chat(chat_id)
        if not chat:
            title = f"Chat with {message.sender_name} ({message.platform})"
            logger.info(f"Creating new social chat: {title} ({chat_id})")
            db.create_chat(
                title=title,
                config={"platform": message.platform, "sender_id": message.sender_id},
                chat_id=chat_id,
            )
