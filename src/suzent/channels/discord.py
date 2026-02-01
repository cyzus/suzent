"""
Discord Channel Driver for Suzent.
"""

import asyncio
from typing import Any, Dict
from suzent.channels.base import SocialChannel, UnifiedMessage
from suzent.logger import get_logger

try:
    import discord
except ImportError:
    discord = None

logger = get_logger(__name__)


# Standard discordant.py pattern: Subclass Client
if discord:

    class SuzentDiscordClient(discord.Client):
        def __init__(self, suzent_channel: "DiscordChannel", *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.suzent_channel = suzent_channel

        async def on_ready(self):
            self.suzent_channel._connected = True
            logger.info(f"Discord logged in as {self.user}")

        async def on_message(self, message):
            # Ignore own messages
            if message.author == self.user:
                return
            await self.suzent_channel._handle_discord_message(message)


class DiscordChannel(SocialChannel):
    """
    Discord Driver using discord.py.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("discord", config)
        self.token = config.get("token")

        if not discord:
            raise ImportError(
                "discord.py not installed. Install with `pip install discord.py`."
            )

        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True  # Required for reading message content
        intents.dm_messages = True

        # Instantiate our custom client
        self.client = SuzentDiscordClient(self, intents=intents)
        self._connected = False

    async def connect(self):
        """Start the Discord client."""
        if not self.token:
            logger.warning("No Discord token provided. Channel disabled.")
            return

        logger.info("Connecting to Discord...")

        # Run properly in background task
        asyncio.create_task(self._run_client())

    async def _run_client(self):
        try:
            await self.client.start(self.token)
        except Exception as e:
            logger.error(f"Discord connection failed: {e}")

    async def disconnect(self):
        """Stop the Discord client."""
        if self.client and self._connected:
            await self.client.close()
            self._connected = False
            logger.info("Discord disconnected.")

    async def _handle_discord_message(self, message: Any):
        """Process incoming message from the client."""
        try:
            # Attachments
            attachments = []
            for att in message.attachments:
                attachments.append(
                    {
                        "type": "file",
                        "id": str(att.id),
                        "filename": att.filename,
                        "url": att.url,
                        "size": att.size,
                        "content_type": att.content_type,
                    }
                )

            unified_msg = UnifiedMessage(
                id=str(message.id),
                content=message.content,
                sender_id=str(message.author.id),
                sender_name=message.author.name,  # or display_name
                platform="discord",
                timestamp=message.created_at.timestamp(),
                thread_id=str(message.channel.id),  # Channel/Thread ID context
                attachments=attachments,
                raw_data={
                    "channel_id": message.channel.id,
                    "guild_id": message.guild.id if message.guild else None,
                },
            )

            await self._invoke_callback(unified_msg)
        except Exception as e:
            logger.error(f"Error handling Discord message: {e}")

    async def send_message(self, target_id: str, content: str, **kwargs) -> bool:
        """
        Send a message.
        target_id: can be Channel ID or User ID.
        """
        if not self.client or not self._connected:
            logger.warning("Discord client not connected.")
            return False

        try:
            channel_id = int(target_id)
            channel = self.client.get_channel(channel_id)
            if not channel:
                # Try fetching via API if not in cache
                try:
                    channel = await self.client.fetch_channel(channel_id)
                except Exception:
                    # Maybe it is a user ID and we want to DM?
                    try:
                        user = await self.client.fetch_user(channel_id)
                        if user:
                            channel = await user.create_dm()
                    except Exception:
                        pass

            if not channel:
                logger.error(f"Discord channel/user {target_id} not found.")
                return False

            await channel.send(content)
            return True
        except Exception as e:
            logger.error(f"Failed to send Discord message to {target_id}: {e}")
            return False

    async def send_file(
        self, target_id: str, file_path: str, caption: str = None, **kwargs
    ) -> bool:
        if not self.client or not self._connected:
            return False

        try:
            channel_id = int(target_id)
            channel = self.client.get_channel(channel_id)
            if not channel:
                try:
                    channel = await self.client.fetch_channel(channel_id)
                except Exception:
                    pass

            if not channel:
                logger.error(f"Discord channel {target_id} not found for file send.")
                return False

            file = discord.File(file_path)
            await channel.send(content=caption, file=file)
            return True
        except Exception as e:
            logger.error(f"Failed to send Discord file to {target_id}: {e}")
            return False
