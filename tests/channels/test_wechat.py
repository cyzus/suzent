import json

import httpx
import pytest

from suzent.channels.wechat import WeChatChannel


def _make_channel(handler) -> WeChatChannel:
    channel = WeChatChannel(
        {
            "bot_token": "token",
            "base_url": "https://ilinkai.weixin.qq.com",
        }
    )
    channel._client = httpx.AsyncClient(
        base_url=channel.base_url,
        transport=httpx.MockTransport(handler),
    )
    return channel


@pytest.mark.asyncio
async def test_wechat_unifies_text_message_and_caches_context():
    channel = WeChatChannel({"bot_token": "token"})
    raw = {
        "msg_id": "msg-1",
        "from_user_id": "user-1@im.wechat",
        "to_user_id": "bot@im.bot",
        "message_type": 1,
        "message_state": 2,
        "context_token": "ctx-1",
        "item_list": [{"type": 1, "text_item": {"text": "hello"}}],
        "create_time": 1700000000000,
    }

    message = channel._to_unified_message(raw)

    assert message is not None
    assert message.id == "msg-1"
    assert message.content == "hello"
    assert message.sender_id == "user-1@im.wechat"
    assert message.platform == "wechat"
    assert message.get_chat_id() == "wechat:user-1@im.wechat"
    assert channel._contexts["user-1@im.wechat"].context_token == "ctx-1"


@pytest.mark.asyncio
async def test_wechat_send_message_uses_cached_context_token():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ret": 0})

    channel = _make_channel(handler)
    channel._to_unified_message(
        {
            "from_user_id": "user-1@im.wechat",
            "message_type": 1,
            "context_token": "ctx-1",
            "item_list": [{"type": 1, "text_item": {"text": "hello"}}],
        }
    )

    try:
        assert await channel.send_message("user-1@im.wechat", "reply") is True
    finally:
        await channel._client.aclose()

    assert len(requests) == 1
    assert requests[0].url.path == "/ilink/bot/sendmessage"
    assert requests[0].headers["Authorization"] == "Bearer token"
    payload = json.loads(requests[0].content.decode("utf-8"))
    assert payload == {
        "msg": {
            "to_user_id": "user-1@im.wechat",
            "message_type": 2,
            "message_state": 2,
            "context_token": "ctx-1",
            "item_list": [{"type": 1, "text_item": {"text": "reply"}}],
        }
    }


@pytest.mark.asyncio
async def test_wechat_send_message_requires_inbound_context():
    channel = _make_channel(lambda request: httpx.Response(200, json={"ret": 0}))

    try:
        assert await channel.send_message("user-1@im.wechat", "reply") is False
    finally:
        await channel._client.aclose()
