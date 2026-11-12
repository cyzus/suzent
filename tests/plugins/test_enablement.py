"""suzent.plugins.enablement: the plugin on/off rules shared with the updater.

The desktop updater runs enablement.py by path on the environment's Python
before syncing it, so the script must not import Suzent and must agree with
PluginManager about which extras to install.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from suzent.plugins import enablement
from suzent.plugins.manager import PluginManager

SCRIPT = Path(enablement.__file__)


def _plugin(root: Path, plugin_id: str, body: str) -> None:
    folder = root / "plugins" / plugin_id
    folder.mkdir(parents=True)
    (folder / "plugin.yaml").write_text(f"id: {plugin_id}\n{body}", encoding="utf-8")


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "checkout"
    _plugin(root, "telegram", "channel: telegram\nextras: [telegram]\n")
    _plugin(root, "feishu", "channel: feishu\nextras: [feishu]\n")
    _plugin(root, "camera", "extras: [camera]\n")
    _plugin(root, "always", "default_enabled: true\nextras: [always]\n")
    (root / "config").mkdir()
    return root


def _state(tmp_path, plugins: dict) -> Path:
    path = tmp_path / "plugins.json"
    path.write_text(json.dumps({"version": 1, "plugins": plugins}), encoding="utf-8")
    return path


def _social(checkout: Path, config: dict) -> None:
    (checkout / "config" / "social.json").write_text(json.dumps(config), "utf-8")


def _manager_extras(checkout: Path, state: Path) -> list[str]:
    return PluginManager(
        [],
        state,
        builtin_dirs=[checkout / "plugins"],
        entry_point_group=None,
        social_config_file=checkout / "config" / "social.json",
    ).enabled_extras()


CASES = {
    "fresh install": ({}, {}),
    "configured chat app": ({}, {"telegram": {"bot_token": "123:abc"}}),
    "chat app switched off in social.json": (
        {},
        {"telegram": {"enabled": False, "bot_token": "123:abc"}},
    ),
    "chat app with no credentials": ({}, {"feishu": {"app_id": ""}}),
    "camera installed": ({"camera": {"enabled": True}}, {}),
    "camera removed": ({"camera": {"enabled": False}}, {}),
    "configured app explicitly removed": (
        {"telegram": {"enabled": False}},
        {"telegram": {"bot_token": "123:abc"}},
    ),
    "default-on plugin turned off": ({"always": {"enabled": False}}, {}),
}


@pytest.mark.parametrize("case", CASES)
def test_script_agrees_with_plugin_manager(case, checkout, tmp_path):
    plugins, social = CASES[case]
    state = _state(tmp_path, plugins)
    _social(checkout, social)

    expected = _manager_extras(checkout, state)

    assert sorted(enablement.builtin_plugin_extras(checkout, state)) == sorted(expected)


def test_expected_extras(checkout, tmp_path):
    _social(checkout, {"telegram": {"bot_token": "123:abc"}})
    state = _state(tmp_path, {"camera": {"enabled": True}})

    assert sorted(enablement.builtin_plugin_extras(checkout, state)) == [
        "always",
        "camera",
        "telegram",
    ]


def test_fresh_install_gets_only_default_on_plugins(checkout, tmp_path):
    assert enablement.builtin_plugin_extras(checkout, tmp_path / "none.json") == [
        "always"
    ]


def test_checkout_without_plugins_gets_social(tmp_path):
    assert enablement.builtin_plugin_extras(tmp_path, tmp_path / "x.json") == ["social"]


def test_prefetch_reads_the_live_social_config(checkout, tmp_path):
    """The updater prefetches into a clean checkout of the target release,
    which has no config/social.json; the live installation's decides."""
    live = tmp_path / "live-social.json"
    live.write_text(json.dumps({"telegram": {"bot_token": "123:abc"}}), "utf-8")
    state = tmp_path / "none.json"

    assert "telegram" not in enablement.builtin_plugin_extras(checkout, state)
    assert "telegram" in enablement.builtin_plugin_extras(checkout, state, live)

    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(checkout), str(state), str(live)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "telegram" in json.loads(result.stdout.strip().splitlines()[-1])


def test_data_dir_social_config_wins_over_the_checkout(checkout, tmp_path):
    """social.json now lives beside plugins.json in the data dir; the
    checkout/live copy is only a fallback for installs not yet migrated."""
    state = tmp_path / "data" / "config" / "plugins.json"
    state.parent.mkdir(parents=True)
    live = tmp_path / "live-social.json"
    live.write_text(json.dumps({"telegram": {"bot_token": "123:abc"}}), "utf-8")

    assert "telegram" in enablement.builtin_plugin_extras(checkout, state, live)

    (state.parent / "social.json").write_text(
        json.dumps({"telegram": {"enabled": False}}), "utf-8"
    )
    assert "telegram" not in enablement.builtin_plugin_extras(checkout, state, live)


def test_tilde_in_the_state_path_is_expanded(checkout, tmp_path, monkeypatch):
    """setup.sh passes "${SUZENT_DATA_DIR}/config/plugins.json" verbatim, so a
    literal "~/custom" must resolve to the home directory."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    state = home / "custom" / "config" / "plugins.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"plugins": {"camera": {"enabled": True}}}), "utf-8")

    extras = enablement.builtin_plugin_extras(
        checkout, Path("~/custom/config/plugins.json")
    )

    assert "camera" in extras


def test_runs_by_path_without_importing_suzent(checkout, tmp_path):
    """Copied out of the source tree and run in isolated mode: any import of
    Suzent would fail, as it would on an environment not yet synced."""
    script = tmp_path / "isolated" / "enablement.py"
    script.parent.mkdir()
    shutil.copy(SCRIPT, script)
    state = _state(tmp_path, {"camera": {"enabled": True}})

    result = subprocess.run(
        [sys.executable, "-I", str(script), str(checkout), str(state)],
        capture_output=True,
        text=True,
        check=True,
    )

    assert sorted(json.loads(result.stdout.strip().splitlines()[-1])) == [
        "always",
        "camera",
    ]


def test_the_repository_plugins_install_nothing_by_default(tmp_path):
    """A fresh install of this repository syncs no plugin extras: chat apps
    and the camera install their packages when the user sets them up."""
    # Only the plugins: the real checkout may hold the developer's own
    # config/social.json, which turns on the chat apps it sets up.
    checkout = tmp_path / "checkout"
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "plugins", checkout / "plugins"
    )
    assert enablement.builtin_plugin_extras(checkout, tmp_path / "none.json") == []
