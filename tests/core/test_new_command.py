from unittest.mock import MagicMock, patch

import pytest

from suzent.core.commands import CommandContext, dispatch
from suzent.core.commands.sess import clear_active_chat_id, get_active_chat_id


@pytest.mark.asyncio
async def test_new_command_creates_and_switches_session() -> None:
    db = MagicMock()
    db.create_chat.return_value = "chat-created-12345678"
    ctx = CommandContext(
        chat_id="social-wechat-default",
        user_id="default-user",
        surface="social",
        platform="wechat",
        sender_id="wechat-user",
    )

    clear_active_chat_id("wechat-user")
    try:
        with patch("suzent.core.commands.sess.get_database", return_value=db):
            response = await dispatch(ctx, "/new Project planning")
    finally:
        active_chat_id = get_active_chat_id("wechat-user", ctx.chat_id)
        clear_active_chat_id("wechat-user")

    assert response == "✅ Created and switched to: [12345678] Project planning"
    assert active_chat_id == "chat-created-12345678"
    db.create_chat.assert_called_once_with(
        title="Project planning", config={"platform": "wechat"}
    )


@pytest.mark.asyncio
async def test_new_command_uses_default_title() -> None:
    db = MagicMock()
    db.create_chat.return_value = "chat-created-12345678"
    ctx = CommandContext(
        chat_id="social-telegram-default",
        user_id="default-user",
        surface="social",
        platform="telegram",
        sender_id="telegram-user",
    )

    clear_active_chat_id("telegram-user")
    try:
        with patch("suzent.core.commands.sess.get_database", return_value=db):
            response = await dispatch(ctx, "/new")
    finally:
        clear_active_chat_id("telegram-user")

    assert response == "✅ Created and switched to: [12345678] New Session"
    db.create_chat.assert_called_once_with(
        title="New Session", config={"platform": "telegram"}
    )
