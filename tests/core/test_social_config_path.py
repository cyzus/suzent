"""social.json moves to the user config dir when PROJECT_DIR is read-only."""

from suzent.config.paths import social_config_path


def test_social_config_lives_in_project_dir_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("SUZENT_PROJECT_DIR", raising=False)
    monkeypatch.setattr("suzent.config.PROJECT_DIR", tmp_path)
    assert social_config_path() == tmp_path / "config" / "social.json"


def test_packaged_social_config_lives_in_user_config_dir(tmp_path, monkeypatch):
    bundled = tmp_path / "app"
    user_config = tmp_path / "data" / "config"
    monkeypatch.setenv("SUZENT_PROJECT_DIR", str(bundled))
    monkeypatch.setattr("suzent.config.PROJECT_DIR", bundled)
    monkeypatch.setattr("suzent.config.USER_CONFIG_DIR", user_config)
    assert social_config_path() == user_config / "social.json"
