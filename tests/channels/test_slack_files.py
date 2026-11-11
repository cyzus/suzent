from suzent.channels.slack import SlackChannel


class _Client:
    def __init__(self) -> None:
        self.uploads: list[dict] = []

    async def files_upload_v2(self, **kwargs) -> None:
        self.uploads.append(kwargs)


def _channel() -> tuple[SlackChannel, _Client]:
    channel = SlackChannel({})
    client = _Client()
    channel.web_client = client
    return channel, client


async def test_file_in_a_thread_is_uploaded_to_that_thread() -> None:
    channel, client = _channel()

    assert await channel.send_file("C123:1700000000.000001", "/tmp/a.pdf", "hi")

    assert client.uploads == [
        {
            "channel": "C123",
            "file": "/tmp/a.pdf",
            "initial_comment": "hi",
            "thread_ts": "1700000000.000001",
        }
    ]


async def test_file_in_a_channel_has_no_thread() -> None:
    channel, client = _channel()

    assert await channel.send_file("D42", "/tmp/a.pdf")

    assert client.uploads[0]["channel"] == "D42"
    assert "thread_ts" not in client.uploads[0]
