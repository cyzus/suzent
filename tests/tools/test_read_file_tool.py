from types import SimpleNamespace

from suzent.tools.base import ToolErrorCode
from suzent.tools.filesystem.read_file_tool import ReadFileTool


class _Resolver:
    def resolve(self, path):
        from pathlib import Path

        return Path(path)


def _ctx(tmp_path):
    deps = SimpleNamespace(
        path_resolver=_Resolver(),
        chat_id="test-chat",
        sandbox_enabled=False,
        custom_volumes=[],
        workspace_root=str(tmp_path),
    )
    return SimpleNamespace(deps=deps)


def test_reads_utf16_text_file(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("hello utf16", encoding="utf-16")

    result = ReadFileTool().forward(_ctx(tmp_path), str(file_path))

    assert result.success
    assert "hello utf16" in result.message


def test_rejects_binary_text_file(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_bytes(b"\x00\x01\x02\x03")

    result = ReadFileTool().forward(_ctx(tmp_path), str(file_path))

    assert not result.success
    assert result.error_code == ToolErrorCode.BINARY_FILE
    assert "binary" in result.message.lower()


def test_rejects_oversized_file(monkeypatch, tmp_path):
    from suzent.tools.filesystem import read_file_tool

    monkeypatch.setattr(read_file_tool, "MAX_READ_FILE_SIZE", 3)
    file_path = tmp_path / "big.txt"
    file_path.write_text("12345", encoding="utf-8")

    result = ReadFileTool().forward(_ctx(tmp_path), str(file_path))

    assert not result.success
    assert result.error_code == ToolErrorCode.FILE_TOO_LARGE
    assert "File too large to read" in result.message


def test_reads_line_slice_with_offset_and_limit(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("a\nb\nc\nd\n", encoding="utf-8")

    result = ReadFileTool().forward(_ctx(tmp_path), str(file_path), offset=1, limit=2)

    assert result.success
    assert "[Lines 2-3 of 4]" in result.message
    normalized = result.message.replace("\r\n", "\n")
    assert "b\n" in normalized
    assert "c\n" in normalized
    assert "d\n" not in normalized
