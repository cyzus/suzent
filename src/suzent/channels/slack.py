"""
Slack Channel Driver for Suzent.
"""

from typing import Any, Dict
from suzent.channels.base import SocialChannel, UnifiedMessage
from suzent.logger import get_logger

try:
    from slack_sdk.web.async_client import AsyncWebClient
    from slack_sdk.socket_mode.aiohttp import SocketModeClient
    from slack_sdk.socket_mode.response import SocketModeResponse
    from slack_sdk.socket_mode.request import SocketModeRequest
except ImportError:
    AsyncWebClient = None
    SocketModeClient = None
    SocketModeResponse = None
    SocketModeRequest = None

    # Define placeholder types for type hinting if checks fail at runtime
    SocketModeClient = Any
    SocketModeRequest = Any

logger = get_logger(__name__)


class SlackChannel(SocialChannel):
    """
    Slack Driver using Socket Mode.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("slack", config)
        self.app_token = config.get("app_token")
        self.bot_token = config.get("bot_token")

        if not self.app_token or not self.bot_token:
            logger.warning("Slack tokens missing. Channel disabled.")
            return

        if not AsyncWebClient:
            raise ImportError(
                "slack_sdk not installed. Install with `pip install slack_sdk`."
            )

        self.web_client = AsyncWebClient(token=self.bot_token)
        self.socket_client = SocketModeClient(
            app_token=self.app_token, web_client=self.web_client
        )
        self._connected = False

    async def connect(self):
        """Start Slack Socket Mode."""
        if not self.socket_client:
            return

        logger.info("Connecting to Slack...")

        # Register listeners
        self.socket_client.socket_mode_request_listeners.append(self._process_event)

        try:
            await self.socket_client.connect()
            self._connected = True
            logger.info("Slack connected via Socket Mode.")
        except Exception as e:
            logger.error(f"Failed to connect to Slack: {e}")

    async def disconnect(self):
        """Disconnect from Slack."""
        if self.socket_client and self._connected:
            await self.socket_client.close()
            self._connected = False
            logger.info("Slack disconnected.")

    async def _process_event(self, client: SocketModeClient, req: SocketModeRequest):
        """Handle incoming Socket Mode requests."""
        # Acknowledge the request immediately
        response = SocketModeResponse(envelope_id=req.envelope_id)
        await client.send_socket_mode_response(response)

        if req.type == "events_api":
            event = req.payload.get("event", {})
            event_type = event.get("type")
            logger.debug(f"Slack Event Received: {event_type}")

            if event_type in ["message", "app_mention"] and not event.get("bot_id"):
                await self._handle_message(event)

    async def _handle_message(self, event: Dict[str, Any]):
        """Process a message event."""
        # Avoid processing other bot messages to prevent loops, though we checked bot_id above
        if "subtype" in event and event["subtype"] == "bot_message":
            return

        try:
            text = event.get("text", "")
            user_id = event.get("user")
            channel_id = event.get("channel")
            ts = event.get("ts")
            thread_ts = event.get("thread_ts")

            # Fetch user info for name (optional optimization: cache this)
            user_info = await self.web_client.users_info(user=user_id)
            user_name = (
                user_info["user"]["real_name"] if user_info.get("ok") else "Unknown"
            )

            attachments = []
            if "files" in event:
                for file in event["files"]:
                    # Download logic would go here. Slack files require auth to download.
                    # For MVP, we'll just note the file.
                    attachments.append(
                        {
                            "type": "file",
                            "id": file.get("id"),
                            "name": file.get("name"),
                            "url_private": file.get(
                                "url_private"
                            ),  # Needs Bearer token to fetch
                        }
                    )
                    # TODO: Implement file download using self.web_client and headers

            unified_msg = UnifiedMessage(
                id=ts,
                content=text,
                sender_id=user_id,
                sender_name=user_name,
                platform="slack",
                timestamp=float(ts),
                thread_id=thread_ts
                or channel_id,  # If no thread, use channel as context? Or just None?
                # Actually, for chat history, channel_id is crucial context.
                # But UnifiedMessage treats thread_id as conversation ID usually?
                # Let's map thread_id to the actual thread, but we need to know the channel too.
                # The `sender_id` usually maps to a user.
                # In Slack, a "Chat" is a Channel.
                # We might need to encode channel in sender_id or handle it differently.
                # For now, let's assume DM or simple channel.
                # NOTE: In Suzent's base.py, get_chat_id use "platform:sender_id".
                # This works for DMs. For channels, everyone would have their own chat ID based on their user ID,
                # which splits the channel history.
                # Ideally, `sender_id` should be the user, but the Conversation ID should be the Channel ID.
                # However, UnifiedMessage doesn't have a separate `chat_id` field, strictly.
                # It has `get_chat_id()`.
                # If we want shared channel history, we might need to hack this or update Base.
                # For now, stick to the Base definition.
                raw_data=event,
            )

            # Special handling for channel context if needed:
            # We can pack channel_id into raw_data or hack sender_id if we want group chat behavior.
            # But the requirement is likely 1:1 agent interaction or just logging it.
            # We'll stick to 1:1 semantics for now (User ID matches Chat ID).
            # If this is a public channel, it might get confusing.

            # Actually, `thread_id` in UnifiedMessage is Optional.
            # If we are in a channel, `channel_id` is the conversation context.
            # We will store `channel_id` in raw_data and let the Agent logic decide.
            # But wait, send_message takes `target_id`.
            # If I receive from User A in Channel X, I should reply to Channel X, not User A (DM).
            # The current Base impl suggests `target_id` comes from `sender_id`.
            # This implies `sender_id` MUST be the return address (Channel ID) for group contexts,
            # OR the system is designed for DMs only.
            # Let's set sender_id to the User, but we might need to route replies carefully.
            # Modifying `get_chat_id` on the fly isn't ideal.
            # Let's look at `send_message`: request takes `target_id`.
            # If the logic calls `send_message(msg.sender_id)`, it goes to DM.
            # If the user wants to reply in channel, we have a mismatch.
            # I will use `channel_id` as the operational ID for replies in `raw_data` or similar.
            # For now, I will map `sender_id` to `channel_id` if it's not a DM?
            # No, that loses user info.
            # I will assume `sender_id` is the user.
            # Implication: The bot replies to the user via DM unless we change this.
            # HACK: If it's a channel, maybe we combine them?
            # Let's verify how Telegram does it.
            # Telegram: sender_id = user.id.
            # send_message(target_id) -> chat_id=target_id.
            # If I get a message from a Group in Telegram, `update.effective_message.chat_id` is the group.
            # `update.effective_user.id` is the user.
            # The Telegram impl uses `str(user.id)` as `sender_id`.
            # So if the bot replies to `sender_id`, it sends a DM to the user, IGNORING the group.
            # This seems to be a limitation of the current Base/Telegram impl.
            # I will follow the pattern: sender_id = user_id.

            await self._invoke_callback(unified_msg)

        except Exception as e:
            logger.error(f"Error handling Slack event: {e}")

    async def send_message(self, target_id: str, content: str, **kwargs) -> bool:
        """
        Send a message.
        target_id: can be a channel ID (C...) or user ID (U...).
        """
        if not self.web_client:
            return False

        try:
            await self.web_client.chat_postMessage(
                channel=target_id, text=content, **kwargs
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send Slack message to {target_id}: {e}")
            return False

    async def send_file(
        self, target_id: str, file_path: str, caption: str = None, **kwargs
    ) -> bool:
        if not self.web_client:
            return False

        try:
            await self.web_client.files_upload_v2(
                channel=target_id, file=file_path, initial_comment=caption, **kwargs
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send Slack file to {target_id}: {e}")
            return False
