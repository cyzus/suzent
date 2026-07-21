"""
WeChat channel implementation using the iLink Bot HTTP API.
"""

from __future__ import annotations

import asyncio
import base64
import random
import time
from dataclasses import dataclass
from typing import Any

import httpx

from suzent.channels.base import SocialChannel, UnifiedMessage
from suzent.logger import logger


DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
DEFAULT_CHANNEL_VERSION = "1.0.2"
TEXT_ITEM_TYPE = 1
USER_MESSAGE_TYPE = 1
BOT_MESSAGE_TYPE = 2
FINISHED_MESSAGE_STATE = 2


@dataclass
class WeChatConversationContext:
    to_user_id: str
    context_token: str
    group_id: str | None = None


def _random_wechat_uin() -> str:
    random_uin = str(random.randint(0, 2**32 - 1))
    return base64.b64encode(random_uin.encode("ascii")).decode("ascii")


def _extract_text(item_list: list[dict[str, Any]]) -> str:
    text_parts: list[str] = []
    for item in item_list:
        item_type = item.get("type")
        if item_type == TEXT_ITEM_TYPE:
            text = (item.get("text_item") or {}).get("text")
            if isinstance(text, str) and text:
                text_parts.append(text)
            continue

        voice_text = (item.get("voice_item") or {}).get("text")
        if isinstance(voice_text, str) and voice_text:
            text_parts.append(voice_text)

    return "\n".join(text_parts)


def _extract_attachments(item_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    for item in item_list:
        item_type = item.get("type")
        if item_type == TEXT_ITEM_TYPE:
            continue

        attachment: dict[str, Any] = {
            "type": {
                2: "image",
                3: "audio",
                4: "file",
                5: "video",
            }.get(item_type, "file"),
            "wechat_item_type": item_type,
            "raw": item,
        }
        attachments.append(attachment)
    return attachments


class WeChatChannel(SocialChannel):
    """
    Driver for Tencent WeChat iLink Bot API.

    The API requires the latest inbound ``context_token`` when sending a reply.
    Suzent routes replies by target ID, so this driver caches the token per
    conversation target after each received message.
    """

    def __init__(self, config: dict[str, Any]):
        super().__init__("wechat", config)
        self.bot_token = config.get("bot_token") or config.get("token")
        self.base_url = (config.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        self.channel_version = config.get("channel_version") or DEFAULT_CHANNEL_VERSION
        self.get_updates_buf = config.get("get_updates_buf", "")
        self.poll_timeout_seconds = float(config.get("poll_timeout_seconds", 40))
        self.login_poll_interval_seconds = float(
            config.get("login_poll_interval_seconds", 2)
        )
        self._client: httpx.AsyncClient | None = None
        self._polling_task: asyncio.Task | None = None
        self._login_task: asyncio.Task | None = None
        self._running = False
        self._contexts: dict[str, WeChatConversationContext] = {}

    async def connect(self) -> None:
        """Start QR login if needed, then long-poll for WeChat messages."""
        if self._running:
            logger.warning("WeChat channel already running, skipping connect.")
            return

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.poll_timeout_seconds + 5),
        )
        self._running = True

        if self.bot_token:
            self._start_polling()
            return

        self._login_task = asyncio.create_task(self._login_and_start_polling())

    async def disconnect(self) -> None:
        """Stop polling and close HTTP resources."""
        self._running = False
        for task in (self._login_task, self._polling_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if self._client:
            await self._client.aclose()
            self._client = None

        logger.info("WeChat channel disconnected.")

    async def send_message(self, target_id: str, content: str, **kwargs) -> bool:
        """Send a text reply to a WeChat conversation."""
        if not self.bot_token or not self._client:
            logger.warning("WeChat channel is not authenticated.")
            return False

        context = self._contexts.get(target_id)
        if not context:
            logger.warning(
                "WeChat cannot send to {} without a cached context_token.",
                target_id,
            )
            return False

        msg: dict[str, Any] = {
            "to_user_id": context.to_user_id,
            "message_type": BOT_MESSAGE_TYPE,
            "message_state": FINISHED_MESSAGE_STATE,
            "context_token": context.context_token,
            "item_list": [{"type": TEXT_ITEM_TYPE, "text_item": {"text": content}}],
        }
        if context.group_id:
            msg["group_id"] = context.group_id

        try:
            response = await self._post("/ilink/bot/sendmessage", {"msg": msg})
            if response.get("ret", 0) != 0:
                logger.error("WeChat sendmessage failed: {}", response)
                return False
            return True
        except Exception as exc:
            logger.error("Failed to send WeChat message to {}: {}", target_id, exc)
            return False

    async def send_file(
        self, target_id: str, file_path: str, caption: str = None, **kwargs
    ) -> bool:
        """WeChat media upload is intentionally left for a later, encrypted CDN pass."""
        file_name = file_path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        notice = f"WeChat file sending is not yet implemented. (File: {file_name})"
        if caption:
            notice = f"{caption}\n\n{notice}"
        return await self.send_message(target_id, notice)

    def _start_polling(self) -> None:
        self._polling_task = asyncio.create_task(self._poll_updates())
        logger.info("WeChat polling started.")

    async def _login_and_start_polling(self) -> None:
        try:
            login = await self._get("/ilink/bot/get_bot_qrcode", params={"bot_type": 3})
            qrcode = login.get("qrcode")
            qrcode_url = login.get("url") or login.get("qrcode_url")
            if not qrcode:
                logger.error("WeChat QR login did not return a qrcode.")
                self._running = False
                return

            if qrcode_url:
                logger.info(
                    "Scan this WeChat bot QR code URL to authenticate: {}", qrcode_url
                )
            else:
                logger.info("WeChat bot QR code created; scan it in the OpenClaw flow.")

            while self._running and not self.bot_token:
                status = await self._get(
                    "/ilink/bot/get_qrcode_status",
                    params={"qrcode": qrcode},
                )
                if status.get("status") == "confirmed":
                    self.bot_token = status.get("bot_token")
                    returned_base_url = status.get("baseurl") or status.get("base_url")
                    if returned_base_url and self._client:
                        self.base_url = str(returned_base_url).rstrip("/")
                        await self._client.aclose()
                        self._client = httpx.AsyncClient(
                            base_url=self.base_url,
                            timeout=httpx.Timeout(self.poll_timeout_seconds + 5),
                        )
                    logger.info(
                        "WeChat bot authenticated. Add the bot_token and base_url to config/social.json to persist it."
                    )
                    self._start_polling()
                    return

                await asyncio.sleep(self.login_poll_interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._running = False
            logger.error("WeChat QR login failed: {}", exc)

    async def _poll_updates(self) -> None:
        while self._running:
            try:
                response = await self._post(
                    "/ilink/bot/getupdates",
                    {
                        "get_updates_buf": self.get_updates_buf,
                        "base_info": {"channel_version": self.channel_version},
                    },
                )
                new_buf = response.get("get_updates_buf")
                if isinstance(new_buf, str) and new_buf:
                    self.get_updates_buf = new_buf

                for raw_msg in response.get("msgs") or []:
                    unified = self._to_unified_message(raw_msg)
                    if unified:
                        await self._invoke_callback(unified)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("WeChat polling failed: {}", exc)
                await asyncio.sleep(2)

    def _to_unified_message(self, raw_msg: dict[str, Any]) -> UnifiedMessage | None:
        if raw_msg.get("message_type") != USER_MESSAGE_TYPE:
            return None

        sender_id = raw_msg.get("from_user_id")
        context_token = raw_msg.get("context_token")
        if not isinstance(sender_id, str) or not isinstance(context_token, str):
            return None

        item_list = raw_msg.get("item_list") or []
        if not isinstance(item_list, list):
            item_list = []

        group_id = raw_msg.get("group_id")
        if not isinstance(group_id, str) or not group_id:
            group_id = None
        target_id = group_id or sender_id
        self._contexts[target_id] = WeChatConversationContext(
            to_user_id=sender_id,
            context_token=context_token,
            group_id=group_id,
        )

        message_id = raw_msg.get("msg_id") or raw_msg.get("message_id")
        if not isinstance(message_id, str) or not message_id:
            message_id = f"{sender_id}:{context_token[:16]}"

        timestamp = raw_msg.get("create_time") or raw_msg.get("timestamp")
        try:
            timestamp_value = float(timestamp)
            if timestamp_value > 10_000_000_000:
                timestamp_value /= 1000.0
        except (TypeError, ValueError):
            timestamp_value = time.time()

        return UnifiedMessage(
            id=message_id,
            content=_extract_text(item_list),
            sender_id=sender_id,
            sender_name=raw_msg.get("sender_name") or sender_id,
            platform="wechat",
            timestamp=timestamp_value,
            thread_id=target_id if group_id else None,
            attachments=_extract_attachments(item_list),
            raw_data=raw_msg,
        )

    async def _get(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self._client:
            raise RuntimeError("WeChat HTTP client is not initialized.")

        response = await self._client.get(
            endpoint,
            params=params,
            headers=self._headers(include_auth=bool(self.bot_token)),
        )
        response.raise_for_status()
        return response.json()

    async def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._client:
            raise RuntimeError("WeChat HTTP client is not initialized.")

        response = await self._client.post(
            endpoint,
            json=payload,
            headers=self._headers(include_auth=True),
        )
        response.raise_for_status()
        return response.json()

    def _headers(self, include_auth: bool) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "X-WECHAT-UIN": _random_wechat_uin(),
        }
        if include_auth and self.bot_token:
            headers["Authorization"] = f"Bearer {self.bot_token}"
        return headers
