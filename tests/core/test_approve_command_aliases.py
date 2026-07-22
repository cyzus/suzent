import pytest

import suzent.core.commands  # noqa: F401 - register command handlers
from suzent.core.commands import CommandContext, dispatch


class _FakeSocialBrain:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def handle_approval_response(
        self,
        platform: str,
        target_id: str,
        approved: bool,
        *,
        sender_id: str | None = None,
        remember: bool = False,
    ) -> None:
        self.calls.append(
            {
                "platform": platform,
                "target_id": target_id,
                "approved": approved,
                "sender_id": sender_id,
                "remember": remember,
            }
        )


@pytest.mark.asyncio
async def test_ya_alias_remembers_social_tool_approval(monkeypatch) -> None:
    brain = _FakeSocialBrain()
    monkeypatch.setattr(
        "suzent.core.social_brain.get_active_social_brain",
        lambda: brain,
    )

    response = await dispatch(
        CommandContext(
            chat_id="social-wechat-room-1",
            user_id="user-1",
            surface="social",
            platform="wechat",
            sender_id="sender-1",
            channel_manager=object(),
        ),
        "/ya",
    )

    assert response == ""
    assert brain.calls == [
        {
            "platform": "wechat",
            "target_id": "room-1",
            "approved": True,
            "sender_id": "sender-1",
            "remember": True,
        }
    ]


@pytest.mark.asyncio
async def test_y_alias_keeps_one_time_social_tool_approval(monkeypatch) -> None:
    brain = _FakeSocialBrain()
    monkeypatch.setattr(
        "suzent.core.social_brain.get_active_social_brain",
        lambda: brain,
    )

    response = await dispatch(
        CommandContext(
            chat_id="social-wechat-room-1",
            user_id="user-1",
            surface="social",
            platform="wechat",
            sender_id="sender-1",
            channel_manager=object(),
        ),
        "/y",
    )

    assert response == ""
    assert brain.calls[0]["remember"] is False
