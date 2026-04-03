from types import SimpleNamespace

from suzent.tools.base import ToolErrorCode
from suzent.tools.filesystem.write_file_tool import WriteFileTool


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
        auto_approve_tools=False,
        tool_approval_policy={},
    )
    return SimpleNamespace(deps=deps)


def test_respects_explicit_deny_policy(tmp_path):
    deps = _ctx(tmp_path).deps
    deps.tool_approval_policy["write_file"] = "always_deny"

    result = WriteFileTool().forward(SimpleNamespace(deps=deps), "sample.txt", "hi")

    assert not result.success
    assert result.error_code == ToolErrorCode.PERMISSION_DENIED
    assert "denied by policy" in result.message


def test_preserves_utf16_encoding_on_overwrite(tmp_path):
    file_path = tmp_path / "sample-utf16.txt"
    file_path.write_text("before", encoding="utf-16")

    result = WriteFileTool().forward(_ctx(tmp_path), str(file_path), "after")

    assert result.success
    assert "Overwrote file" in result.message
    assert file_path.read_text(encoding="utf-16") == "after"


def test_returns_no_changes_for_identical_content(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("same", encoding="utf-8")

    result = WriteFileTool().forward(_ctx(tmp_path), str(file_path), "same")

    assert result.success
    assert "No changes" in result.message


def test_rejects_binary_overwrite(tmp_path):
    file_path = tmp_path / "binary.dat"
    file_path.write_bytes(b"\x00\x01\x02\x03")

    result = WriteFileTool().forward(_ctx(tmp_path), str(file_path), "text")

    assert not result.success
    assert result.error_code == ToolErrorCode.BINARY_FILE
    assert "Refusing to overwrite binary file" in result.message


def test_rejects_oversized_file(monkeypatch, tmp_path):
    from suzent.tools.filesystem import write_file_tool

    monkeypatch.setattr(write_file_tool, "MAX_WRITE_FILE_SIZE", 3)
    file_path = tmp_path / "big.txt"
    file_path.write_text("12345", encoding="utf-8")

    result = WriteFileTool().forward(_ctx(tmp_path), str(file_path), "new")

    assert not result.success
    assert result.error_code == ToolErrorCode.FILE_TOO_LARGE
    assert "File too large to overwrite" in result.message
