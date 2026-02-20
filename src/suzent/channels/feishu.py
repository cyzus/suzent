"""
Feishu (Lark) Channel Driver for Suzent.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Any, Callable, Optional

from suzent.channels.base import SocialChannel, UnifiedMessage
from suzent.logger import get_logger

# Import Lark SDK
try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        P2ImMessageReceiveV1,
        CreateMessageRequest,
        CreateMessageRequestBody,
        GetMessageResourceRequest,
    )
except ImportError:
    lark = None
    P2ImMessageReceiveV1 = object  # Fallback for type hinting
    CreateMessageRequest = object
    CreateMessageRequestBody = object
    GetMessageResourceRequest = object

logger = get_logger(__name__)


class FeishuChannel(SocialChannel):
    """
    Feishu (Lark) Driver using Protocol v1 and WebSocket (Long Connection).
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Feishu Channel.

        Args:
            config: Dictionary containing 'app_id', 'app_secret', etc.
        """
        self.app_id = config.get("app_id")
        self.app_secret = config.get("app_secret")
        self.verification_token = config.get("verification_token")
        self.encrypt_key = config.get("encrypt_key")

        if not self.app_id or not self.app_secret:
            raise ValueError("FeishuChannel requires 'app_id' and 'app_secret'.")

        self.name = "feishu"
        self.on_message: Optional[Callable[[UnifiedMessage], Any]] = None

        if not lark:
            logger.error(
                "lark-oapi not installed. Install with `pip install lark-oapi`."
            )
            raise ImportError("lark-oapi package missing")

        # HTTP Client for API calls (Sending messages)
        self.client = (
            lark.Client.builder()
            .app_id(self.app_id)
            .app_secret(self.app_secret)
            .log_level(lark.LogLevel.INFO)
            .build()
        )

        # WebSocket Client for Events (Receiving messages)
        self.ws_client = None
        self.main_loop = None  # Capture main loop for thread-safe dispatch

    async def connect(self):
        """Start the WebSocket client."""
        logger.info(f"Connecting to Feishu via WebSocket (App ID: {self.app_id})...")

        self.main_loop = asyncio.get_running_loop()

        # Define Event Handler
        def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
            logger.debug("Feishu WS: Received raw event in thread.")
            # Dispatch handling to the MAIN event loop (where Suzent server runs)
            # This ensures queue operations and DB access happen in the correct context
            if self.main_loop:
                future = asyncio.run_coroutine_threadsafe(
                    self._handle_event(data), self.main_loop
                )

                # Add callback to log errors from the future
                def check_error(f):
                    try:
                        f.result()
                    except Exception as e:
                        logger.error(f"Feishu dispatch error: {e}")

                future.add_done_callback(check_error)
            else:
                logger.error("Main loop not captured, cannot dispatch Feishu event.")

        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
            .build()
        )

        def run_ws_client():
            """Run WS client in a dedicated event loop in this thread."""
            # Create a new loop for this thread's WS client
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # CRITICAL FIX: lark-oapi uses a global 'loop' variable captured at import time.
            # We must monkey-patch it to use our thread's loop, otherwise it tries to use
            # the main server loop and fails with "This event loop is already running".
            try:
                import lark_oapi.ws.client

                lark_oapi.ws.client.loop = loop
            except ImportError:
                logger.warning("Could not patch lark_oapi.ws.client.loop")

            logger.debug("Creating Feishu WS Client in dedicated thread...")
            client = lark.ws.Client(
                self.app_id,
                self.app_secret,
                event_handler=event_handler,
                log_level=lark.LogLevel.INFO,
            )
            self.ws_client = client

            # This blocks until disconnected
            try:
                client.start()
            except Exception as e:
                logger.error(f"Feishu WS Client error: {e}")
            finally:
                loop.close()

        # Run WS client in background thread
        import threading

        self._ws_thread = threading.Thread(target=run_ws_client, daemon=True)
        self._ws_thread.start()
        logger.info("Feishu WebSocket client started in isolated background thread.")

    async def disconnect(self):
        """Stop the client."""
        if self.ws_client:
            # There isn't a clean 'stop' method in public docs easily found,
            # usually just closing the process or relying on daemon thread.
            logger.info("Disconnecting Feishu (Daemon thread will close with app).")
            pass

    def set_callback(self, callback: Callable[[UnifiedMessage], Any]):
        self.on_message = callback

    async def _handle_event(self, data: P2ImMessageReceiveV1):
        """Process incoming Feishu message event."""
        try:
            event = data.event
            msg = event.message
            sender = event.sender

            # sender_id priority: union_id > open_id > user_id
            # Note: We prefer open_id for simpler bot interactions if available?
            # Actually, let's use what we have and detect type.
            u_id = sender.sender_id.union_id
            o_id = sender.sender_id.open_id
            us_id = sender.sender_id.user_id

            logger.debug(
                f"Feishu Message IDs - Union: {u_id}, Open: {o_id}, User: {us_id}"
            )

            sender_id = u_id or o_id or us_id

            # Name unavailable in event usually, need to fetch user info or use ID
            # For now use ID or "Feishu User"
            sender_name = f"Feishu User ({sender_id[:6]})"

            if hasattr(msg.content, "decode"):
                try:
                    msg.content = msg.content.decode("utf-8")
                except Exception:
                    pass

            try:
                msg_content = json.loads(msg.content)
            except Exception:
                msg_content = {}
                text_content = msg.content
            text_content = ""
            attachments = []

            logger.debug(f"Message Type: {msg.message_type}")
            if msg.message_type == "text":
                text_content = msg_content.get("text", "")

            elif msg.message_type == "image":
                image_key = msg_content.get("image_key")
                local_path = await self._download_file(
                    image_key, msg.message_id, "image", ".jpg"
                )
                if local_path:
                    attachments.append(
                        {
                            "type": "image",
                            "path": local_path,
                            "filename": f"{image_key}.jpg",
                            "id": image_key,
                        }
                    )
                text_content = "[Image]"

            elif msg.message_type == "file":
                file_key = msg_content.get("file_key")
                file_name = msg_content.get("file_name", "downloaded_file")
                _, ext = os.path.splitext(file_name)

                local_path = await self._download_file(
                    file_key, msg.message_id, "file", ext, filename=file_name
                )
                if local_path:
                    attachments.append(
                        {
                            "type": "file",
                            "path": local_path,
                            "filename": file_name,
                            "id": file_key,
                        }
                    )
                text_content = f"[File: {file_name}]"

            elif msg.message_type == "post":
                # Rich text handling - simplify to text for now
                # Post content structure is complex [[Elements]]
                # Extract plain text
                text_content = self._extract_post_text(msg_content)

            # Construct Unified Message
            unified_msg = UnifiedMessage(
                id=msg.message_id,
                content=text_content,
                sender_id=sender_id,
                sender_name=sender_name,
                platform="feishu",
                timestamp=float(msg.create_time) / 1000.0,
                attachments=attachments,
                thread_id=msg.root_id or msg.parent_id,
                raw_data=None,
            )

            await self._invoke_callback(unified_msg)

        except Exception as e:
            logger.error(f"Error handling Feishu event: {e}")

    def _extract_post_text(self, content: dict) -> str:
        """Simple extraction of text from rich post."""
        try:
            # structure: content['title'], content['content'] = [[Elem]]
            title = content.get("title", "")
            lines = []
            if title:
                lines.append(title)

            for paragraph in content.get("content", []):
                line = ""
                for elem in paragraph:
                    if elem.get("tag") == "text":
                        line += elem.get("text", "")
                    elif elem.get("tag") == "a":
                        line += elem.get("text", "")
                lines.append(line)
            return "\n".join(lines)
        except Exception:
            return "[Rich Text Post]"

    async def _download_file(
        self,
        file_key: str,
        message_id: str,
        type_str: str,
        ext: str,
        filename: str = None,
    ) -> Optional[str]:
        """Download file/image from Feishu."""
        try:
            final_filename = filename or f"{file_key}{ext}"
            local_path = self._get_upload_path(final_filename)

            # Create Request
            request = (
                GetMessageResourceRequest.builder()
                .message_id(message_id)
                .file_key(file_key)
                .type(type_str)
                .build()
            )

            # Execute - blocking call, wrap in executor
            def do_download():
                response = self.client.im.v1.message_resource.get(request)
                if not response.success():
                    logger.error(
                        f"Feishu download failed for {file_key}: {response.code} {response.msg}"
                    )
                    return None

                # Write stream
                with open(local_path, "wb") as f:
                    f.write(response.file.read())
                return str(local_path)

            return await asyncio.to_thread(do_download)

        except Exception as e:
            logger.error(f"Error downloading Feishu resource {file_key}: {e}")
            return None

    async def send_message(self, target_id: str, content: str, **kwargs) -> bool:
        """Send a text message."""
        try:
            # Construct JSON content
            content_json = json.dumps({"text": content})

            req_body = (
                CreateMessageRequestBody.builder()
                .receive_id(target_id)
                .msg_type("text")
                .content(content_json)
                .build()
            )

            req = (
                CreateMessageRequest.builder()
                .receive_id_type("open_id")
                .request_body(req_body)
                .build()
            )

            # Using open_id defaults? Target ID must match type.
            # Assuming target_id is open_id. If union_id, need to change param.
            # We'll try open_id first (most common for bot interactions).
            # If target_id starts with 'ou_', it's open_id. 'on_' is union_id.
            if target_id.startswith("on_"):
                req = (
                    CreateMessageRequest.builder()
                    .receive_id_type("union_id")
                    .request_body(req_body)
                    .build()
                )

            resp = await asyncio.to_thread(
                lambda: self.client.im.v1.message.create(req)
            )

            if not resp.success():
                logger.error(
                    f"Failed to send Feishu message: {resp.code} {resp.msg} - ReqID: {resp.request_id}"
                )
                logger.error(
                    f"Failed Body: {resp.raw.content if hasattr(resp, 'raw') else 'Unknown'}"
                )
                return False
            logger.info(f"Sent Feishu message to {target_id} (Success)")
            return True

        except Exception as e:
            logger.error(f"Error sending Feishu message: {e}")
            return False

    async def send_file(
        self, target_id: str, file_path: str, caption: str = None, **kwargs
    ) -> bool:
        """Send a file/image."""
        # For simplicity in MVP, define sending file logic later or just send text
        await self.send_message(
            target_id,
            f"File sending not yet implemented for Feishu. (File: {Path(file_path).name})",
        )
        return True
