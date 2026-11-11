import json
from pathlib import Path
from types import SimpleNamespace

from suzent.channels.feishu import FeishuChannel


class _Api:
    def __init__(self, key_name: str | None = None, key: str = "") -> None:
        self.requests = []
        self.key_name = key_name
        self.key = key

    def create(self, request):
        self.requests.append(request)
        data = SimpleNamespace(**({self.key_name: self.key} if self.key_name else {}))
        return SimpleNamespace(success=lambda: True, data=data, code=0, msg="ok")


def _channel() -> tuple[FeishuChannel, SimpleNamespace]:
    channel = FeishuChannel({"app_id": "app", "app_secret": "secret"})
    v1 = SimpleNamespace(
        image=_Api("image_key", "img_1"),
        file=_Api("file_key", "file_1"),
        message=_Api(),
    )
    channel.client = SimpleNamespace(im=SimpleNamespace(v1=v1))
    return channel, v1


def _sent(v1: SimpleNamespace) -> list[tuple[str, str, dict]]:
    return [
        (
            request.receive_id_type,
            request.request_body.msg_type,
            json.loads(request.request_body.content),
        )
        for request in v1.message.requests
    ]


async def test_small_images_are_posted_inline(tmp_path: Path) -> None:
    image = tmp_path / "chart.png"
    image.write_bytes(b"png")
    channel, v1 = _channel()

    assert await channel.send_file("oc_group", str(image), caption="Chart")
    assert _sent(v1) == [
        ("chat_id", "text", {"text": "Chart"}),
        ("chat_id", "image", {"image_key": "img_1"}),
    ]


async def test_other_files_are_uploaded_with_their_feishu_type(tmp_path: Path) -> None:
    report = tmp_path / "report.docx"
    report.write_bytes(b"doc")
    channel, v1 = _channel()

    assert await channel.send_file("ou_user", str(report))
    upload = v1.file.requests[0].request_body
    assert (upload.file_type, upload.file_name) == ("doc", "report.docx")
    assert _sent(v1) == [("open_id", "file", {"file_key": "file_1"})]
