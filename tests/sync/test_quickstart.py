from pathlib import Path

import pytest

from suzent.sync import quickstart as quickstart_module
from suzent.sync.quickstart import (
    normalize_repo_name,
    quickstart_github_sync,
)


def test_normalize_repo_name():
    assert normalize_repo_name("My-Brain") == "my-brain"


def test_quickstart_initializes_local_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "github-sync"
    monkeypatch.setattr(quickstart_module, "DEFAULT_REPO_DIR", repo)
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))

    result = quickstart_github_sync(authenticate_github=False)

    assert result["success"] is True
    assert (repo / ".git").exists()
    assert result["repo_name"] == "suzent-brain"


def test_quickstart_custom_repo_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "github-sync"
    monkeypatch.setattr(quickstart_module, "DEFAULT_REPO_DIR", repo)
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))

    result = quickstart_github_sync(
        repo_name="custom-brain",
        authenticate_github=False,
    )

    assert result["repo_name"] == "custom-brain"
