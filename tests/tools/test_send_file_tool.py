import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from suzent.tools import send_file_tool
from suzent.tools.send_file_tool import SendFileTool


class _Resolver:
    def __init__(self, root: Path) -> None:
        self.root = root

    def resolve(self, raw: str) -> Path:
        path = (self.root / raw).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("outside the workspace")
        return path


class _Channels:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.sent: list[tuple[str, str, str, str | None]] = []

    async def send_file(self, platform, target, path, caption=None):
        self.sent.append((platform, target, Path(path).name, caption))
        return self.result


def _ctx(tmp_path: Path, social: dict | None = None, channels=None):
    return SimpleNamespace(
        deps=SimpleNamespace(
            social_context=social or {},
            channel_manager=channels,
            event_loop=None,
        )
    )


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "report.pdf").write_bytes(b"%PDF")
    (root / "chart.png").write_bytes(b"png")
    monkeypatch.setattr(
        "suzent.tools.send_file_tool.get_or_create_path_resolver",
        lambda deps: _Resolver(root),
    )
    return root


async def test_desktop_and_phone_get_the_files_as_attachments(workspace: Path) -> None:
    result = await SendFileTool().forward(
        _ctx(workspace), ["report.pdf", "report.pdf", "chart.png"]
    )

    assert result.success
    assert result.metadata["saved_paths"] == [
        str(workspace / "report.pdf"),
        str(workspace / "chart.png"),
    ]


async def test_rejects_paths_outside_the_workspace_and_missing_files(
    workspace: Path,
) -> None:
    outside = await SendFileTool().forward(_ctx(workspace), ["../secret.txt"])
    missing = await SendFileTool().forward(_ctx(workspace), ["nope.pdf"])

    assert not outside.success and "outside" in outside.message
    assert not missing.success and "not an existing file" in missing.message


async def test_social_chat_sends_through_its_channel_with_caption_once(
    workspace: Path,
) -> None:
    channels = _Channels()
    result = await SendFileTool().forward(
        _ctx(workspace, {"platform": "telegram", "target_id": "42"}, channels),
        ["report.pdf", "chart.png"],
        caption="Here you go",
    )

    assert result.success
    assert channels.sent == [
        ("telegram", "42", "report.pdf", "Here you go"),
        ("telegram", "42", "chart.png", None),
    ]
    assert len(result.metadata["delivered_paths"]) == 2


async def test_reports_oversized_and_rejected_files(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        __import__(
            "suzent.tools.send_file_tool"
        ).tools.send_file_tool.PLATFORM_FILE_LIMITS,
        "discord",
        3,
    )
    channels = _Channels(result=False)
    result = await SendFileTool().forward(
        _ctx(workspace, {"platform": "discord", "target_id": "7"}, channels),
        ["report.pdf", "chart.png"],
    )

    assert not result.success
    assert "report.pdf: larger than discord" in result.message
    assert "chart.png: the chat app rejected it" in result.message
    assert [name for _, _, name, _ in channels.sent] == ["chart.png"]


async def test_wechat_is_reported_as_unsupported(workspace: Path) -> None:
    channels = _Channels()
    result = await SendFileTool().forward(
        _ctx(workspace, {"platform": "wechat", "target_id": "w"}, channels),
        ["report.pdf"],
    )

    assert not result.success and "can't receive files" in result.message
    assert channels.sent == []


async def test_dispatches_to_the_channel_loop_from_another_loop(
    workspace: Path,
) -> None:
    channel_loop = asyncio.new_event_loop()
    import threading

    thread = threading.Thread(target=channel_loop.run_forever, daemon=True)
    thread.start()
    try:
        channels = _Channels()
        ctx = _ctx(workspace, {"platform": "slack", "target_id": "C1"}, channels)
        ctx.deps.event_loop = channel_loop
        result = await SendFileTool().forward(ctx, ["report.pdf"])
        assert result.success and channels.sent[0][0] == "slack"
    finally:
        channel_loop.call_soon_threadsafe(channel_loop.stop)
        thread.join(5)
        channel_loop.close()
