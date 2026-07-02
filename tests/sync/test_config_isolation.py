"""Regression: sync must honor SUZENT_DATA_DIR set after import, so tests (and
alternate profiles) never write into the real ~/.suzent/config."""

from pathlib import Path

from suzent.sync.service import GitHubSyncService
from suzent.sync.payload import SyncPayloadBuilder


def test_service_profiles_path_honors_data_dir_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    svc = GitHubSyncService()
    # Must resolve under the overridden data dir, not the frozen real config.
    assert Path(svc.profiles_path) == tmp_path / "config" / "sync_profiles.json"
    assert str(tmp_path) in str(svc.profiles_path)


def test_payload_builder_dirs_honor_data_dir_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path))
    b = SyncPayloadBuilder()
    assert b.data_dir == tmp_path
    assert b.user_config_dir == tmp_path / "config"
    assert b.user_skills_dir == tmp_path / "skills" / "user"
