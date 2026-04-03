from types import SimpleNamespace

from suzent.tools.base import ToolErrorCode
from suzent.tools.filesystem.edit_file_tool import EditFileTool


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


def test_rejects_noop_replacement(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("hello", encoding="utf-8")

    result = EditFileTool().forward(
        _ctx(tmp_path), str(file_path), "hello", "hello", replace_all=False
    )

    assert not result.success
    assert result.error_code == ToolErrorCode.NO_OP_CHANGE
    assert "identical" in result.message


def test_rejects_ambiguous_single_replace(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("foo\nfoo\n", encoding="utf-8")

    result = EditFileTool().forward(
        _ctx(tmp_path), str(file_path), "foo", "bar", replace_all=False
    )

    assert not result.success
    assert result.error_code == ToolErrorCode.AMBIGUOUS_MATCH
    assert "Found 2 matches" in result.message
    assert file_path.read_text(encoding="utf-8") == "foo\nfoo\n"


def test_replace_all_updates_all_matches(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("foo\nfoo\n", encoding="utf-8")

    result = EditFileTool().forward(
        _ctx(tmp_path), str(file_path), "foo", "bar", replace_all=True
    )

    assert result.success
    assert "Replaced 2 occurrence(s)" in result.message
    assert file_path.read_text(encoding="utf-8") == "bar\nbar\n"


def test_preserves_utf16_encoding(tmp_path):
    file_path = tmp_path / "sample-utf16.txt"
    file_path.write_text("alpha beta", encoding="utf-16")

    result = EditFileTool().forward(
        _ctx(tmp_path), str(file_path), "beta", "gamma", replace_all=False
    )

    assert result.success
    assert "Replaced 1 occurrence(s)" in result.message
    assert file_path.read_text(encoding="utf-16") == "alpha gamma"


def test_normalizes_inserted_newlines_to_crlf(tmp_path):
    file_path = tmp_path / "sample-crlf.txt"
    file_path.write_text("start\r\nend\r\n", encoding="utf-8", newline="")

    result = EditFileTool().forward(
        _ctx(tmp_path), str(file_path), "start", "a\nb", replace_all=False
    )

    assert result.success
    assert "Replaced 1 occurrence(s)" in result.message
    with open(file_path, "r", encoding="utf-8", newline="") as handle:
        assert handle.read() == "a\r\nb\r\nend\r\n"
