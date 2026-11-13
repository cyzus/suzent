"""Which session a chat-app message reaches, and how /sess moves it."""

from unittest.mock import MagicMock, patch

import pytest

from suzent.channels.base import UnifiedMessage
from suzent.channels.session_binding import SHARED_DIRECT_KEY, get_binding
from suzent.core.commands import CommandContext, dispatch
from suzent.core.commands.sess import get_active_chat_id
from suzent.core.focal_agent import FOCAL_CHAT_ID
from suzent.core.social_brain import SocialBrain


def _message(platform: str, *, direct: bool, thread_id: str | None = None):
    return UnifiedMessage(
        id="m1",
        content="hi",
        sender_id="111",
        sender_name="alice",
        platform=platform,
        thread_id=thread_id,
        is_direct=direct,
    )


def test_direct_messages_from_every_app_go_to_regent():
    brain = SocialBrain(None, regent_direct_messages=True)
    for platform in ("telegram", "slack"):
        route = brain._conversation_route(_message(platform, direct=True))
        assert route == (SHARED_DIRECT_KEY, FOCAL_CHAT_ID)


def test_group_chats_keep_their_own_session():
    brain = SocialBrain(None, regent_direct_messages=True)
    route = brain._conversation_route(
        _message("telegram", direct=False, thread_id="-42")
    )
    assert route == ("telegram:111", "social-telegram--42")


def test_without_the_setting_each_app_has_its_own_chat():
    brain = SocialBrain(None)
    route = brain._conversation_route(_message("telegram", direct=True))
    assert route == ("telegram:111", "social-telegram-111")


@pytest.mark.asyncio
async def test_switch_on_one_app_holds_on_another_and_survives_reload():
    db = MagicMock()
    db.get_chat.return_value = MagicMock(id="project-chat-1234", title="Project")

    def ctx(platform: str) -> CommandContext:
        return CommandContext(
            chat_id=FOCAL_CHAT_ID,
            user_id="default-user",
            surface="social",
            platform=platform,
            sender_id="111",
            binding_key=SHARED_DIRECT_KEY,
        )

    with patch("suzent.core.commands.sess.get_database", return_value=db):
        await dispatch(ctx("telegram"), "/sess switch project-chat-1234")
    # The binding is on disk, so another app (or a restart) reads the same one.
    assert get_binding(SHARED_DIRECT_KEY) == "project-chat-1234"
    assert get_active_chat_id(SHARED_DIRECT_KEY, FOCAL_CHAT_ID) == "project-chat-1234"

    response = await dispatch(ctx("slack"), "/sess reset")
    assert response == "✅ Back to Regent"
    assert get_active_chat_id(SHARED_DIRECT_KEY, FOCAL_CHAT_ID) == FOCAL_CHAT_ID
