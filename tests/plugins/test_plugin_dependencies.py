"""Plugins that bring packages: built-in defaults, extras, installs and upgrades."""

import asyncio
import importlib
import json
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
from typer.testing import CliRunner

from suzent.plugins import PluginManager
from suzent.plugins import deps

REPO_PLUGINS = Path(__file__).resolve().parents[2] / "plugins"


def _write(root: Path, plugin_id: str, manifest: str, code: str | None = None) -> Path:
    plugin_dir = root / plugin_id
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.yaml").write_text(f"id: {plugin_id}\n{manifest}")
    if code is not None:
        (plugin_dir / "__init__.py").write_text(code)
    return plugin_dir


def _manager(tmp_path: Path, builtin: Path, user: Path | None = None) -> PluginManager:
    return PluginManager(
        [user or tmp_path / "user"],
        tmp_path / "plugins.json",
        builtin_dirs=[builtin],
        deps_root=tmp_path / "deps",
        entry_point_group=None,
        social_config_file=tmp_path / "social.json",
    )


def _social(tmp_path: Path, **platforms) -> None:
    (tmp_path / "social.json").write_text(json.dumps(platforms))


def test_shipped_chat_apps_are_separate_plugins_off_until_set_up(tmp_path):
    manager = _manager(tmp_path, REPO_PLUGINS)

    records = manager.discover()

    assert {"telegram", "slack", "discord", "feishu"} <= set(records)
    assert "social" not in records
    assert manager.resolve("lark").id == "feishu"
    for plugin_id in ("telegram", "slack", "discord", "feishu"):
        record = records[plugin_id]
        assert record.source == "builtin" and not record.has_code
        assert record.manifest.channel == plugin_id
        assert record.manifest.extras == [plugin_id]
        assert not record.enabled
    assert manager.enabled_extras() == []


def test_a_chat_app_already_set_up_turns_its_plugin_on(tmp_path):
    _social(
        tmp_path,
        telegram={"enabled": True, "token": "123:abc", "allowed_users": []},
        slack={"enabled": True, "app_token": "", "bot_token": ""},
        discord={"enabled": False, "token": "secret"},
    )
    manager = _manager(tmp_path, REPO_PLUGINS)

    assert manager.enabled_ids() == {"telegram"}
    assert manager.enabled_extras() == ["telegram"]
    assert manager.for_channel("telegram").id == "telegram"


def test_removing_a_chat_app_is_remembered_and_switches_it_off(tmp_path):
    _social(tmp_path, telegram={"enabled": True, "token": "123:abc"})
    manager = _manager(tmp_path, REPO_PLUGINS)

    manager.set_enabled("telegram", False)

    assert not manager.resolve("telegram").enabled
    assert manager.enabled_extras() == []
    social = json.loads((tmp_path / "social.json").read_text())
    assert social["telegram"] == {"enabled": False, "token": "123:abc"}

    manager.set_enabled("telegram", True)
    social = json.loads((tmp_path / "social.json").read_text())
    assert social["telegram"]["enabled"] is True


def test_only_builtin_plugins_may_default_to_on(tmp_path):
    user = tmp_path / "user"
    _write(user, "pushy", "default_enabled: true\n")
    manager = _manager(tmp_path, tmp_path / "none", user)

    assert not manager.resolve("pushy").enabled


def test_packages_only_plugin_loads_without_code(tmp_path):
    builtin = tmp_path / "builtin"
    _write(builtin, "chat", "extras: [chat]\ndefault_enabled: true\n")
    manager = _manager(tmp_path, builtin)

    [record] = manager.records()

    assert record.status == "loaded"
    assert manager.tool_classes() == []


def test_install_syncs_every_enabled_extra(tmp_path, monkeypatch):
    builtin = tmp_path / "builtin"
    _write(builtin, "chat", "extras: [chat]\ndefault_enabled: true\n")
    _write(builtin, "voice", "extras: [voice]\n")
    manager = _manager(tmp_path, builtin)
    calls = []
    monkeypatch.setattr(deps, "sync_extras", lambda root, extras: calls.append(extras))

    manager.install_dependencies(manager.resolve("voice"), tmp_path)

    assert calls == [["chat", "voice"]]


def test_third_party_requirements_go_to_their_own_directory(tmp_path, monkeypatch):
    user = tmp_path / "user"
    _write(user, "weather", "dependencies: ['requests-mock>=1']\n")
    manager = _manager(tmp_path, tmp_path / "none", user)
    calls = []
    monkeypatch.setattr(
        deps, "install_requirements", lambda reqs, target: calls.append((reqs, target))
    )

    manager.install_dependencies(manager.resolve("weather"), tmp_path)

    assert calls == [(["requests-mock>=1"], tmp_path / "deps" / "weather")]


def test_extra_requirements_reads_suzent_metadata():
    names = {name.lower() for name in deps.extra_requirements("telegram")}

    assert names == {"python-telegram-bot", "markdown"}
    assert {n.lower() for n in deps.extra_requirements("slack")} == {"slack-sdk"}
    assert deps.extra_requirements("no-such-extra") == []


def test_missing_packages_reports_absent_requirements(tmp_path):
    missing = deps.missing_packages(
        [], ["surely-not-installed-pkg>=1", "pyyaml"], tmp_path / "deps"
    )

    assert missing == ["surely-not-installed-pkg"]


def test_sync_command_shapes():
    assert deps.sync_command("uv", ["social"], development=True, inexact=True) == [
        "uv",
        "sync",
        "--frozen",
        "--inexact",
        "--extra",
        "social",
        "--extra",
        "dev",
    ]
    assert deps.sync_command("uv", []) == ["uv", "sync", "--frozen"]


def test_sync_extras_needs_a_source_checkout(tmp_path):
    with pytest.raises(deps.DependencyError, match="pip install"):
        deps.sync_extras(tmp_path, ["social"])


def test_upgrade_sync_follows_enabled_plugins(tmp_path, monkeypatch):
    cli_main = importlib.import_module("suzent.cli.main")

    monkeypatch.setattr("suzent.config.paths.USER_CONFIG_DIR", tmp_path)
    root = tmp_path / "checkout"
    (root / "plugins").mkdir(parents=True)
    _write(root / "plugins", "telegram", "extras: [telegram]\nchannel: telegram\n")
    _write(root / "plugins", "slack", "extras: [slack]\nchannel: slack\n")
    (root / "config").mkdir()
    (root / "config" / "social.json").write_text(
        json.dumps({"telegram": {"enabled": True, "token": "123:abc"}})
    )
    (root / ".suzent-bootstrap-complete").write_text("")

    assert cli_main._backend_sync_args(root) == [
        "uv",
        "sync",
        "--frozen",
        "--extra",
        "telegram",
    ]

    (tmp_path / "plugins.json").write_text(
        json.dumps({"version": 1, "plugins": {"telegram": {"enabled": False}}})
    )
    assert cli_main._backend_sync_args(root) == ["uv", "sync", "--frozen"]


def test_cli_status_lists_missing_packages(tmp_path, monkeypatch):
    from suzent.cli.plugin import plugin_app

    user = tmp_path / "user"
    _write(user, "weather", "dependencies: ['surely-not-installed-pkg']\n")
    manager = _manager(tmp_path, tmp_path / "none", user)
    manager.set_enabled("weather", True)
    monkeypatch.setattr("suzent.plugins.get_plugin_manager", lambda: manager)

    result = CliRunner().invoke(plugin_app, ["status"])

    assert result.exit_code == 1
    assert "missing: surely-not-installed-pkg" in result.output


@pytest.fixture
def plugin_api(tmp_path, monkeypatch):
    from suzent.routes import plugin_routes

    builtin = tmp_path / "builtin"
    _write(
        builtin, "telegram", "extras: [telegram]\nchannel: telegram\naliases: [tg]\n"
    )
    _write(
        builtin, "tools", "description: adds tools\n", code="def register(ctx): pass\n"
    )
    manager = _manager(tmp_path, builtin)
    monkeypatch.setattr(plugin_routes, "get_plugin_manager", lambda: manager)
    installs, reloads = [], []
    monkeypatch.setattr(
        manager, "install_dependencies", lambda record, root: installs.append(record.id)
    )

    async def fake_reload(request):
        reloads.append(True)

    monkeypatch.setattr(plugin_routes, "_reload_social", fake_reload)
    # The server loads plugins at startup; the API reports against that.
    manager.load()
    app = Starlette(
        routes=[
            Route("/plugins", plugin_routes.list_plugins, methods=["GET"]),
            Route(
                "/plugins/{name}/install",
                plugin_routes.install_plugin,
                methods=["POST"],
            ),
            Route(
                "/plugins/{name}/remove", plugin_routes.remove_plugin, methods=["POST"]
            ),
        ]
    )
    return TestClient(app), manager, installs, reloads


def test_api_install_by_alias_installs_packages_and_reloads_chat_apps(plugin_api):
    client, manager, installs, reloads = plugin_api

    response = client.post("/plugins/tg/install")

    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert response.json()["restartRequired"] is False
    assert installs == ["telegram"] and reloads == [True]


def test_api_code_plugin_loads_without_a_restart(plugin_api):
    client, manager, installs, reloads = plugin_api

    data = client.post("/plugins/tools/install").json()

    assert data["enabled"] is True
    assert data["status"] == "loaded"
    assert data["restartRequired"] is False
    assert reloads == []
    listed = {p["id"]: p for p in client.get("/plugins").json()}
    assert listed["tools"]["restartRequired"] is False

    data = client.post("/plugins/tools/remove").json()

    assert data["enabled"] is False and data["restartRequired"] is False


def test_api_rejects_unknown_plugins(plugin_api):
    client, *_ = plugin_api

    assert client.post("/plugins/left-pad/install").status_code == 404


def test_api_reports_failed_installs(plugin_api, monkeypatch):
    client, manager, *_ = plugin_api

    def fail(record, root):
        raise deps.DependencyError("network down")

    monkeypatch.setattr(manager, "install_dependencies", fail)

    response = client.post("/plugins/telegram/install")

    assert response.status_code == 502
    assert response.json()["error"] == "network down"
    assert manager.resolve("telegram").enabled


def test_removed_chat_app_plugin_keeps_its_app_off(tmp_path, monkeypatch):
    from suzent.channels import manager as channel_manager

    manager = _manager(tmp_path, REPO_PLUGINS)
    manager.set_enabled("telegram", False)
    monkeypatch.setattr("suzent.plugins.get_plugin_manager", lambda: manager)

    channels = channel_manager.ChannelManager()
    channels.load_drivers_from_config({"telegram": {"enabled": True, "token": "x"}})

    assert channels.channels == {}
    assert channel_manager._plugin_allows("wechat")
    manager.set_enabled("telegram", True)
    assert channel_manager._plugin_allows("telegram")


def test_api_remove_stops_chat_apps(plugin_api):
    client, manager, installs, reloads = plugin_api
    manager.set_enabled("telegram", True)

    data = client.post("/plugins/telegram/remove").json()

    assert data["enabled"] is False
    assert reloads == [True]


def test_saving_chat_app_settings_turns_its_plugin_on(tmp_path, monkeypatch):
    from suzent.routes import config_routes

    manager = _manager(tmp_path, REPO_PLUGINS)
    manager.set_enabled("telegram", False)
    installs, reloads = [], []
    monkeypatch.setattr("suzent.plugins.get_plugin_manager", lambda: manager)
    monkeypatch.setattr(
        manager, "install_dependencies", lambda record, root: installs.append(record.id)
    )
    monkeypatch.setattr(manager, "missing_packages", lambda record: ["sdk"])

    async def fake_reload(app, config):
        reloads.append(config)

    monkeypatch.setattr("suzent.server.reload_social", fake_reload)
    config = {
        "telegram": {"enabled": True, "token": "123:abc"},
        "slack": {"enabled": True, "app_token": "", "bot_token": ""},
    }

    asyncio.run(config_routes._apply_social_config(None, config))

    assert manager.enabled_ids() == {"telegram"}
    assert installs == ["telegram"]
    assert reloads == [config]
