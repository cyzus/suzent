from pathlib import Path

import pytest

from suzent.tools.filesystem.path_resolver import PathResolver


def test_resolve_rejects_unc_paths(tmp_path):
    resolver = PathResolver(
        chat_id="test-chat",
        sandbox_enabled=False,
        sandbox_data_path=str(tmp_path / "sandbox"),
        workspace_root=str(tmp_path / "workspace"),
    )

    with pytest.raises(ValueError, match="UNC paths are not supported"):
        resolver.resolve(r"\\server\share\file.txt")


def test_resolve_allows_workspace_relative_paths(tmp_path):
    resolver = PathResolver(
        chat_id="test-chat",
        sandbox_enabled=False,
        sandbox_data_path=str(tmp_path / "sandbox"),
        workspace_root=str(tmp_path / "workspace"),
    )

    resolved = resolver.resolve("notes.txt")

    assert isinstance(resolved, Path)
    assert str(resolved).endswith("notes.txt")


def test_resolve_persistence_uploads_uses_session_directory_in_host_mode(tmp_path):
    resolver = PathResolver(
        chat_id="test-chat",
        sandbox_enabled=False,
        sandbox_data_path=str(tmp_path / "sandbox"),
        workspace_root=str(tmp_path / "workspace"),
    )

    resolved = resolver.resolve("/persistence/uploads/example.txt")

    assert (
        resolved
        == (
            tmp_path / "sandbox" / "sessions" / "test-chat" / "uploads" / "example.txt"
        ).resolve()
    )
