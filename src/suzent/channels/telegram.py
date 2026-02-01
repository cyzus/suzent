"""
Telegram channel implementation.
"""

import os
from typing import Any, Optional
from suzent.logger import get_logger
from suzent.channels.base import SocialChannel, UnifiedMessage

try:
    from telegram import Update
    from telegram.ext import (
        Application,
        ApplicationBuilder,
        ContextTypes,
        MessageHandler,
        filters,
    )
except ImportError:
    # Handle optional dependency
    Update = Any
    Application = Any

logger = get_logger(__name__)


class TelegramChannel(SocialChannel):
    """
    Driver for Telegram Bot API.
    """

    def __init__(self, config: dict[str, Any]):
        super().__init__("telegram", config)
        self.token = config.get("token")
        self.app: Optional[Application] = None
        self._running = False

    async def connect(self):
        """Start the Telegram bot poller."""
        if not self.token:
            logger.warning("No Telegram token provided. Channel disabled.")
            return

        try:
            self.app = ApplicationBuilder().token(self.token).build()

            # Register handlers
            # Handle text and captions
            self.app.add_handler(
                MessageHandler(
                    filters.TEXT & (~filters.COMMAND), self._handle_text_message
                )
            )
            # Handle photos/documents
            self.app.add_handler(
                MessageHandler(
                    filters.PHOTO | filters.Document.ALL, self._handle_media_message
                )
            )

            # Initialize and start
            await self.app.initialize()
            await self.app.start()

            # Run polling in extended loop or use updater?
            # Since we are inside an existing generic async loop, we should use updater.start_polling()
            # BUT updater.start_polling() is blocking or designed for main thread usually?
            # python-telegram-bot v20+ async architecture:
            # app.updater.start_polling() starts a background task.

            await self.app.updater.start_polling()
            self._running = True
            logger.info("Telegram polling started.")

        except Exception as e:
            logger.error(f"Failed to connect to Telegram: {e}")
            raise

    async def disconnect(self):
        """Stop the bot."""
        if self.app and self._running:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            self._running = False
            logger.info("Telegram disconnected.")

    async def send_message(self, target_id: str, content: str, **kwargs) -> bool:
        """Send a message to a chat ID."""
        if not self.app:
            return False

        try:
            # target_id in UnifiedMessage context is the user_id or chat_id
            await self.app.bot.send_message(chat_id=target_id, text=content, **kwargs)
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message to {target_id}: {e}")
            return False

    async def send_file(
        self, target_id: str, file_path: str, caption: str = None, **kwargs
    ) -> bool:
        """Send a file."""
        if not self.app:
            return False

        try:
            # Detect type or just send as document?
            # sending as document is safest for generic files
            with open(file_path, "rb") as file:
                await self.app.bot.send_document(
                    chat_id=target_id, document=file, caption=caption, **kwargs
                )
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram file to {target_id}: {e}")
            return False

    async def _download_file_to_temp(
        self, file_id: str, suggested_name: str = None
    ) -> tuple[str, str]:
        """Helper to download a file from Telegram to a temp directory."""
        new_file = await self.app.bot.get_file(file_id)

        # Determine filename
        if suggested_name:
            filename = suggested_name
        else:
            # Infer extension from file_path
            ext = ".bin"
            if new_file.file_path:
                ext = os.path.splitext(new_file.file_path)[1] or ".jpg"
            filename = f"{file_id}{ext}"

        local_path = self._get_upload_path(filename)
        await new_file.download_to_drive(custom_path=local_path)

        return str(local_path), filename

    async def _handle_text_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Internal handler for text messages."""
        if not update.effective_message:
            return

        msg = update.effective_message
        user = update.effective_user

        unified_msg = UnifiedMessage(
            id=str(msg.message_id),
            content=msg.text or "",
            sender_id=str(user.id),
            sender_name=user.full_name or user.username or "Unknown",
            platform="telegram",
            timestamp=msg.date.timestamp() if msg.date else 0,
            thread_id=None,  # could be message_thread_id for topics
            raw_data=update.to_dict(),
        )

        await self._invoke_callback(unified_msg)

    async def _handle_media_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Internal handler for media messages."""
        if not update.effective_message:
            return

        msg = update.effective_message
        user = update.effective_user

        caption = msg.caption or ""
        attachments = []

        # Handle Photo (get largest)
        if msg.photo:
            try:
                largest_photo = msg.photo[-1]
                local_path, filename = await self._download_file_to_temp(
                    largest_photo.file_id
                )

                attachments.append(
                    {
                        "type": "image",
                        "path": local_path,
                        "filename": filename,
                        "size": largest_photo.file_size,
                        "id": largest_photo.file_id,
                    }
                )
                logger.info(f"Downloaded Telegram photo to {local_path}")
            except Exception as e:
                logger.error(f"Failed to download Telegram photo: {e}")

        # Handle Document
        if msg.document:
            try:
                doc = msg.document
                local_path, filename = await self._download_file_to_temp(
                    doc.file_id, suggested_name=doc.file_name
                )

                # Detect if image based on mime
                is_image = doc.mime_type and doc.mime_type.startswith("image/")

                attachments.append(
                    {
                        "type": "image" if is_image else "file",
                        "path": local_path,
                        "filename": filename,
                        "size": doc.file_size,
                        "mime": doc.mime_type,
                        "id": doc.file_id,
                    }
                )
                logger.info(f"Downloaded Telegram document to {local_path}")
            except Exception as e:
                logger.error(f"Failed to download Telegram document: {e}")

        unified_msg = UnifiedMessage(
            id=str(msg.message_id),
            content=caption,  # Content is caption for media
            sender_id=str(user.id),
            sender_name=user.full_name or "Unknown",
            platform="telegram",
            attachments=attachments,
            raw_data=update.to_dict(),
        )

        await self._invoke_callback(unified_msg)
