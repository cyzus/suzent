from pathlib import Path

import pytest

from suzent.sync.quickstart import _is_ephemeral_repo_path, _resolve_quickstart_target


def test_ephemeral_pytest_path_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path / "data"))
    pytest_dir = tmp_path / "pytest-of-user" / "test_x" / "github-sync"
    pytest_dir.mkdir(parents=True)
    resolved = _resolve_quickstart_target(pytest_dir)
    assert "pytest-of" not in str(resolved)
    assert resolved.name == "github-sync"


def test_real_path_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path / "data"))
    custom = tmp_path / "my-sync"
    custom.mkdir()
    assert _resolve_quickstart_target(custom) == custom.resolve()
    assert not _is_ephemeral_repo_path(custom)
