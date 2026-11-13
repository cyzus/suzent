import pytest

from suzent.channels.base import SocialChannel
from suzent.channels.manager import ChannelManager


class RecordingChannel(SocialChannel):
    def __init__(self) -> None:
        super().__init__("recording", {})
        self.messages: list[str] = []

    async def connect(self):
        return None

    async def disconnect(self):
        return None

    async def send_message(self, target_id: str, content: str, **kwargs) -> bool:
        self.messages.append(content)
        return True

    async def send_file(
        self, target_id: str, file_path: str, caption: str = None, **kwargs
    ) -> bool:
        return True


@pytest.mark.asyncio
async def test_send_message_never_exposes_pua_to_social_driver():
    manager = ChannelManager()
    channel = RecordingChannel()
    manager.register_channel(channel)

    await manager.send_message(
        "recording",
        "recipient",
        "Fact\ue200cite\ue202t0_src_1\ue201.",
        citation_sources=[
            {
                "id": "t0_src_1",
                "type": "webpage",
                "title": "Evidence",
                "url": "https://example.com/evidence",
            }
        ],
    )

    assert channel.messages == [
        "Fact [1].\n\nSources:\n[1] Evidence — https://example.com/evidence"
    ]
    assert not any("\ue200" <= char <= "\uf8ff" for char in channel.messages[0])


@pytest.mark.asyncio
async def test_send_stream_holds_markers_split_across_chunks():
    manager = ChannelManager()
    channel = RecordingChannel()
    manager.register_channel(channel)

    async def stream():
        yield "Fact\ue200ci"
        yield "te\ue202t0_src_1\ue201."

    await manager.send_stream("recording", "recipient", stream())

    assert channel.messages == [
        "Fact [1].\n\nSources:\n[1] Source unavailable (t0_src_1)"
    ]


class StreamingChannel(RecordingChannel):
    async def send_stream(self, target_id: str, stream, **kwargs) -> bool:
        self.messages.append("".join([chunk async for chunk in stream]))
        return True


@pytest.mark.asyncio
@pytest.mark.parametrize("channel_cls", [RecordingChannel, StreamingChannel])
async def test_send_stream_splits_messages_on_breaks(channel_cls):
    from suzent.channels.base import MESSAGE_BREAK

    manager = ChannelManager()
    channel = channel_cls()
    manager.register_channel(channel)

    async def stream():
        for part in [
            MESSAGE_BREAK,
            "First ",
            "part",
            MESSAGE_BREAK,
            MESSAGE_BREAK,
            "Second",
            MESSAGE_BREAK,
        ]:
            yield part

    assert await manager.send_stream("recording", "recipient", stream()) is True
    assert channel.messages == ["First part", "Second"]
