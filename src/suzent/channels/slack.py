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

            # Determine conversation context (Channel ID or Channel:ThreadTS)
            conversation_id = channel_id
            if thread_ts:
                conversation_id = f"{channel_id}:{thread_ts}"

            unified_msg = UnifiedMessage(
                id=ts,
                content=text,
                sender_id=user_id,
                sender_name=user_name,
                platform="slack",
                timestamp=float(ts),
                thread_id=conversation_id,
                raw_data=event,
            )

            await self._invoke_callback(unified_msg)

        except Exception as e:
            logger.error(f"Error handling Slack event: {e}")

    async def send_message(self, target_id: str, content: str, **kwargs) -> bool:
        """
        Send a message.
        target_id: can be a channel ID (C...), user ID (U...), or composite (C...:p...) for threads.
        """
        if not self.web_client:
            return False

        try:
            channel = target_id
            thread_ts = None

            if ":" in target_id:
                # Handle composite ID for threads
                parts = target_id.split(":")
                if len(parts) == 2:
                    channel, thread_ts = parts

            await self.web_client.chat_postMessage(
                channel=channel, text=content, thread_ts=thread_ts, **kwargs
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
