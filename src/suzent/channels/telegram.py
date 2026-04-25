"""
Telegram channel implementation.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from suzent.logger import get_logger
from suzent.channels.base import SocialChannel, UnifiedMessage

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.constants import ParseMode
    from telegram.error import TelegramError
    from telegram.ext import (
        ApplicationBuilder,
        CallbackQueryHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
except ImportError:
    # Handle optional dependency
    Update = Any
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None

logger = get_logger(__name__)


def _to_html(text: str) -> str:
    """Convert Markdown to Telegram-compatible HTML via markdown + BeautifulSoup."""
    import markdown
    from bs4 import BeautifulSoup, NavigableString, Tag

    html = markdown.markdown(text, extensions=["tables", "fenced_code"])
    soup = BeautifulSoup(html, "html.parser")

    # Tags Telegram HTML supports directly
    ALLOWED = {"b", "strong", "i", "em", "u", "s", "code", "pre", "a", "blockquote"}

    def convert(node) -> str:
        if isinstance(node, NavigableString):
            return str(node)

        assert isinstance(node, Tag)
        tag = node.name
        inner = "".join(convert(c) for c in node.children)

        if tag in ALLOWED:
            if tag == "a":
                href = node.get("href", "")
                return f'<a href="{href}">{inner}</a>'
            return f"<{tag}>{inner}</{tag}>"

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            return f"\n<b>{inner}</b>\n"

        if tag == "table":
            # Extract all rows via BeautifulSoup — no manual parsing needed
            rows = [
                [cell.get_text() for cell in row.find_all(["th", "td"])]
                for row in node.find_all("tr")
            ]
            if not rows:
                return inner
            import unicodedata

            def dw(s: str) -> int:
                return sum(
                    2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s
                )

            def ljust_dw(s: str, w: int) -> str:
                return s + " " * max(w - dw(s), 0)

            cols = max(len(r) for r in rows)
            for r in rows:
                while len(r) < cols:
                    r.append("")
            widths = [max(dw(r[c]) for r in rows) for c in range(cols)]
            sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
            lines = [sep]
            for i, row in enumerate(rows):
                lines.append(
                    "| "
                    + " | ".join(ljust_dw(row[c], widths[c]) for c in range(cols))
                    + " |"
                )
                if i == 0:
                    lines.append(sep)
            lines.append(sep)
            return "<pre>" + "\n".join(lines) + "</pre>"

        if tag in ("ul", "ol"):
            return "\n" + inner + "\n"

        if tag == "li":
            return "• " + inner + "\n"

        if tag == "p":
            return inner + "\n"

        if tag == "br":
            return "\n"

        # Everything else: just keep the text content
        return inner

    return "".join(convert(c) for c in soup.children).strip()


def _split_chunks(text: str, limit: int) -> list[str]:
    """Split text into chunks no larger than `limit` characters."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks


class TelegramChannel(SocialChannel):
    """
    Driver for Telegram Bot API.
    """

    def __init__(self, config: dict[str, Any]):
        super().__init__("telegram", config)
        self.token = config.get("token")
        self.app = None  # telegram.ext.Application or None
        self._running = False
        # nonce → list of (label, value) for pending option menus
        self._option_sessions: dict[str, list[tuple[str, str]]] = {}

    @property
    def supports_interactive(self) -> bool:
        return True

    async def connect(self):
        """Start the Telegram bot poller."""
        if not self.token:
            logger.warning("No Telegram token provided. Channel disabled.")
            return

        if self._running:
            logger.warning("Telegram channel already running, skipping connect.")
            return

        try:
            self.app = ApplicationBuilder().token(self.token).build()

            # Register handlers
            # Handle text and captions
            self.app.add_handler(
                MessageHandler(
                    filters.TEXT | filters.COMMAND, self._handle_text_message
                )
            )
            # Handle photos/documents
            self.app.add_handler(
                MessageHandler(
                    filters.PHOTO | filters.Document.ALL, self._handle_media_message
                )
            )
            # Handle inline keyboard button presses
            self.app.add_handler(CallbackQueryHandler(self._handle_callback_query))

            # Initialize and start
            await self.app.initialize()
            await self.app.start()

            # Register slash commands for Telegram's autocomplete menu
            try:
                from telegram import BotCommand
                from suzent.core.commands.base import list_commands

                tg_cmds = [
                    BotCommand(m.name, m.description[:256])
                    for m in list_commands(surface="social")
                    if m.description
                ]
                if tg_cmds:
                    await self.app.bot.set_my_commands(tg_cmds)
                    logger.info(f"Registered {len(tg_cmds)} Telegram commands")
            except Exception as e:
                logger.warning(f"Failed to register Telegram commands: {e}")

            await self.app.updater.start_polling(drop_pending_updates=True)
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

    def _parse_chat_id(self, target_id: str):
        try:
            return int(target_id)
        except ValueError:
            return target_id

    async def send_message(self, target_id: str, content: str, **kwargs) -> bool:
        """Send a message to a chat ID, with MarkdownV2 and plain-text fallback."""
        logger.info(f"Telegram sending message to {target_id}: {content[:20]}...")
        if not self.app:
            logger.error("Telegram app not initialized.")
            return False

        chat_id_val = self._parse_chat_id(target_id)

        # Split into ≤4096-char chunks (Telegram limit)
        chunks = _split_chunks(content, 4096)
        for chunk in chunks:
            try:
                await self.app.bot.send_message(
                    chat_id=chat_id_val,
                    text=_to_html(chunk),
                    parse_mode=ParseMode.HTML,
                    **kwargs,
                )
            except TelegramError:
                # Fallback to plain text if Markdown parse fails
                try:
                    await self.app.bot.send_message(
                        chat_id=chat_id_val, text=chunk, **kwargs
                    )
                except Exception as e:
                    logger.error(f"Failed to send Telegram message to {target_id}: {e}")
                    return False
        logger.info("Telegram message sent successfully.")
        return True

    async def send_stream(
        self, target_id: str, stream, min_interval: float = 1.5
    ) -> bool:
        """
        Stream content to Telegram using edit_message_text (typewriter effect).
        `stream` is an async iterable of str chunks.
        Edits the same message every `min_interval` seconds to avoid rate limits.
        """
        if not self.app:
            return False

        chat_id_val = self._parse_chat_id(target_id)
        accumulated = ""
        sent_msg = None
        last_edit = 0.0

        async def _keep_typing():
            """Send typing action every 4 s until cancelled (Telegram clears it after 5 s)."""
            try:
                while True:
                    try:
                        await self.app.bot.send_chat_action(
                            chat_id=chat_id_val, action="typing"
                        )
                    except Exception:
                        pass
                    await asyncio.sleep(4)
            except asyncio.CancelledError:
                pass

        typing_task = asyncio.create_task(_keep_typing())
        try:
            async for chunk in stream:
                accumulated += chunk
                now = asyncio.get_event_loop().time()

                if sent_msg is None:
                    # First chunk — send the initial message and stop typing indicator
                    typing_task.cancel()
                    try:
                        sent_msg = await self.app.bot.send_message(
                            chat_id=chat_id_val,
                            text=_to_html(accumulated) or "…",
                            parse_mode=ParseMode.HTML,
                        )
                    except TelegramError:
                        sent_msg = await self.app.bot.send_message(
                            chat_id=chat_id_val,
                            text=accumulated or "…",
                        )
                    last_edit = now
                elif now - last_edit >= min_interval:
                    display = _to_html(accumulated)
                    try:
                        await self.app.bot.edit_message_text(
                            chat_id=chat_id_val,
                            message_id=sent_msg.message_id,
                            text=display,
                            parse_mode=ParseMode.HTML,
                        )
                    except TelegramError:
                        try:
                            await self.app.bot.edit_message_text(
                                chat_id=chat_id_val,
                                message_id=sent_msg.message_id,
                                text=accumulated,
                            )
                        except Exception:
                            pass
                    last_edit = now

            # Final edit with complete content
            if sent_msg and accumulated:
                try:
                    await self.app.bot.edit_message_text(
                        chat_id=chat_id_val,
                        message_id=sent_msg.message_id,
                        text=_to_html(accumulated),
                        parse_mode=ParseMode.HTML,
                    )
                except TelegramError:
                    try:
                        await self.app.bot.edit_message_text(
                            chat_id=chat_id_val,
                            message_id=sent_msg.message_id,
                            text=accumulated,
                        )
                    except Exception:
                        pass
            elif not sent_msg and accumulated:
                await self.send_message(target_id, accumulated)

        except Exception as e:
            logger.error(f"Telegram stream error for {target_id}: {e}")
            return False
        finally:
            typing_task.cancel()
        return True

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

    async def send_options(
        self,
        target_id: str,
        text: str,
        options: list[tuple[str, str]],
        columns: int = 2,
    ) -> bool:
        """Send options as an inline keyboard. Falls back to text if bot not ready."""
        if not self.app or InlineKeyboardMarkup is None:
            return await super().send_options(target_id, text, options, columns)

        import uuid

        nonce = uuid.uuid4().hex[:8]
        self._option_sessions[nonce] = options

        keyboard = self._build_options_keyboard(nonce, options, 0, columns)
        markup = InlineKeyboardMarkup(keyboard)
        try:
            await self.app.bot.send_message(
                chat_id=self._parse_chat_id(target_id),
                text=_to_html(text),
                reply_markup=markup,
                parse_mode=ParseMode.HTML,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send options to {target_id}: {e}")
            return False

    def _build_options_keyboard(
        self,
        nonce: str,
        options: list[tuple[str, str]],
        page: int,
        columns: int,
        page_size: int = 16,
    ) -> list[list]:
        start = page * page_size
        page_opts = options[start : start + page_size]

        rows = []
        for i in range(0, len(page_opts), columns):
            row = []
            for j in range(columns):
                idx = i + j
                if idx >= len(page_opts):
                    break
                label, _ = page_opts[idx]
                global_idx = start + idx
                row.append(
                    InlineKeyboardButton(
                        label, callback_data=f"op:{nonce}:{global_idx}"
                    )
                )
            rows.append(row)

        total_pages = (len(options) + page_size - 1) // page_size
        if total_pages > 1:
            nav = []
            if page > 0:
                nav.append(
                    InlineKeyboardButton(
                        "◀ Prev", callback_data=f"pg:{nonce}:{page - 1}:{columns}"
                    )
                )
            if page < total_pages - 1:
                nav.append(
                    InlineKeyboardButton(
                        "Next ▶", callback_data=f"pg:{nonce}:{page + 1}:{columns}"
                    )
                )
            if nav:
                rows.append(nav)

        return rows

    async def _handle_callback_query(
        self, update: Update, context: "ContextTypes.DEFAULT_TYPE"
    ):
        """Handle inline keyboard button presses."""
        query = update.callback_query
        if not query or not query.data:
            return

        import time

        data = query.data
        sender_id = str(query.from_user.id)

        # Option selected: op:{nonce}:{global_index}
        if data.startswith("op:"):
            parts = data.split(":", 2)
            if len(parts) != 3:
                await query.answer()
                return
            nonce, idx_str = parts[1], parts[2]
            try:
                idx = int(idx_str)
            except ValueError:
                await query.answer()
                return

            options = self._option_sessions.get(nonce)
            if not options or idx >= len(options):
                await query.answer("Option no longer available.")
                return

            _, value = options[idx]
            thread_id = str(query.message.chat.id) if query.message else sender_id
            synthetic = UnifiedMessage(
                id=f"cb:{query.id}",
                content=value,
                sender_id=sender_id,
                sender_name=query.from_user.full_name or sender_id,
                platform="telegram",
                timestamp=time.time(),
                thread_id=thread_id,
            )
            await query.answer()
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            await self._invoke_callback(synthetic)
            return

        # Pagination: pg:{nonce}:{page}:{columns}
        if data.startswith("pg:"):
            parts = data.split(":", 3)
            if len(parts) < 3:
                await query.answer()
                return
            try:
                nonce = parts[1]
                page = int(parts[2])
                columns = int(parts[3]) if len(parts) > 3 else 2
            except (ValueError, IndexError):
                await query.answer()
                return

            options = self._option_sessions.get(nonce)
            if not options:
                await query.answer("Session expired.")
                return

            keyboard = self._build_options_keyboard(nonce, options, page, columns)
            markup = InlineKeyboardMarkup(keyboard)
            await query.answer()
            try:
                await query.edit_message_reply_markup(reply_markup=markup)
            except Exception:
                pass
            return

        await query.answer()

    async def _handle_text_message(
        self, update: Update, context: "ContextTypes.DEFAULT_TYPE"
    ):
        """Internal handler for text messages."""
        print(f"DEBUG: Telegram update received: {update}")
        logger.debug(f"Telegram raw update: {update}")
        if not update.effective_message:
            logger.debug("Telegram update verified: No effective message found.")
            return

        msg = update.effective_message
        user = update.effective_user

        print(f"DEBUG: Processing message from {user.id}: {msg.text}")
        logger.info(
            f"Telegram message received from {user.id} in chat {msg.chat.id}: {msg.text}"
        )

        unified_msg = UnifiedMessage(
            id=str(msg.message_id),
            content=msg.text or "",
            sender_id=str(user.id),
            sender_name=user.full_name or user.username or "Unknown",
            platform="telegram",
            timestamp=msg.date.timestamp() if msg.date else 0,
            thread_id=str(msg.chat.id),
            raw_data=update.to_dict(),
        )

        await self._invoke_callback(unified_msg)

    async def _handle_media_message(
        self, update: Update, context: "ContextTypes.DEFAULT_TYPE"
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
