"""User state is kept in the data dir, never in PROJECT_DIR.

A packaged (MSIX) install ships PROJECT_DIR read-only, so every user-editable
config file is read from and written to USER_CONFIG_DIR. A source checkout
that kept them in PROJECT_DIR/config has them copied over once.
"""

import json

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.config import paths
from suzent.config.paths import user_config_file


def _snapshot(root):
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / "config").mkdir(parents=True)
    user = tmp_path / "data" / "config"
    user.mkdir(parents=True)
    monkeypatch.setattr(paths, "PROJECT_DIR", project)
    monkeypatch.setattr(paths, "USER_CONFIG_DIR", user)
    return project, user


def test_returns_the_data_dir_path_without_creating_it(dirs):
    project, user = dirs
    path = user_config_file("social.json")
    assert path == user / "social.json"
    assert not path.exists()
    assert _snapshot(project) == {}


def test_migrates_a_checkout_copy_once_and_leaves_the_original(dirs):
    project, user = dirs
    legacy = project / "config" / "social.json"
    legacy.write_text('{"telegram": {"enabled": true}}', encoding="utf-8")

    path = user_config_file("social.json")
    assert path.read_text(encoding="utf-8") == legacy.read_text(encoding="utf-8")
    assert legacy.exists()  # copied, not moved: a rollback still finds it

    # The data-dir copy now wins; a later change to the checkout is ignored.
    path.write_text('{"telegram": {"enabled": false}}', encoding="utf-8")
    legacy.write_text('{"changed": true}', encoding="utf-8")
    assert json.loads(user_config_file("social.json").read_text()) == {
        "telegram": {"enabled": False}
    }


def test_social_routes_never_write_to_project_dir(dirs, monkeypatch):
    project, user = dirs
    from suzent.routes import config_routes

    (project / "config" / "social.json").write_text(
        json.dumps({"telegram": {"enabled": True, "bot_token": "old"}}),
        encoding="utf-8",
    )
    before = _snapshot(project)

    async def _no_apply(app, social_config):
        return None

    monkeypatch.setattr(config_routes, "_apply_social_config", _no_apply)
    app = Starlette(
        routes=[
            Route("/social", config_routes.get_social_config, methods=["GET"]),
            Route("/social", config_routes.save_social_config, methods=["POST"]),
        ]
    )
    client = TestClient(app)

    assert client.get("/social").status_code == 200
    response = client.post(
        "/social", json={"config": {"telegram": {"bot_token": "new"}}}
    )
    assert response.status_code == 200, response.text

    saved = json.loads((user / "social.json").read_text(encoding="utf-8"))
    assert saved["telegram"]["bot_token"] == "new"
    assert _snapshot(project) == before


def test_default_config_and_permissions_write_to_the_data_dir(dirs):
    project, user = dirs
    from suzent.logger import get_logger
    from suzent.permissions.loader import (
        load_permission_overrides,
        persist_global_command_rule,
    )
    from suzent.routes import config_routes

    (project / "config" / "default.yaml").write_text("model: a\n", "utf-8")
    (project / "config" / "permissions.yaml").write_text(
        "default_permission_mode: auto\n", "utf-8"
    )
    before = _snapshot(project)

    data = config_routes._load_default_config_file()
    assert data == {"model": "a"}
    config_routes._save_default_config_file({**data, "model": "b"})
    assert "model: b" in (user / "default.yaml").read_text(encoding="utf-8")

    logger = get_logger(__name__)
    overrides = load_permission_overrides(project, logger, user)
    assert overrides["default_permission_mode"] == "auto"
    assert persist_global_command_rule(
        project,
        logger,
        tool_name="ShellTool",
        command_pattern="git status",
        action="allow",
    )
    assert "git status" in (user / "permissions.yaml").read_text(encoding="utf-8")

    assert _snapshot(project) == before
