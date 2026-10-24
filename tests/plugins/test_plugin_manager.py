"""Plugin discovery, enablement and registration."""

import asyncio
import json
import textwrap
import uuid
from pathlib import Path

import pytest
from typer.testing import CliRunner

from suzent.core.commands import base as commands_base
from suzent.plugins import PluginManager
from suzent.tools.base import Tool, ToolResult

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples" / "plugins"


@pytest.fixture
def restore_commands():
    """Plugin commands land in the process-wide registry; undo them per test."""
    meta = list(commands_base._META)
    registered = list(commands_base.bot_cli.registered_commands)
    yield
    commands_base._META[:] = meta
    commands_base.bot_cli.registered_commands[:] = registered


def _write_plugin(root: Path, plugin_id: str, body: str, **manifest) -> Path:
    plugin_dir = root / plugin_id
    plugin_dir.mkdir(parents=True)
    fields = {"id": plugin_id, "version": "1.0.0", **manifest}
    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(f"{key}: {value}" for key, value in fields.items()) + "\n"
    )
    (plugin_dir / "__init__.py").write_text(textwrap.dedent(body))
    return plugin_dir


def _manager(tmp_path: Path, *dirs: Path, enabled: list[str] = ()) -> PluginManager:
    state = tmp_path / "plugins.json"
    plugins = {plugin_id: {"enabled": True} for plugin_id in enabled}
    state.write_text(json.dumps({"version": 1, "plugins": plugins}))
    return PluginManager(
        list(dirs) or [tmp_path / "plugins"], state, entry_point_group=None
    )


_TOOL_PLUGIN = """
from suzent.tools.base import Tool, ToolResult


class EchoTool(Tool):
    name = "PluginEchoTool"
    tool_name = "plugin_echo"
    description = "Echo the text back."

    def forward(self, text: str) -> ToolResult:
        return ToolResult.success_result(text)


def register(ctx):
    ctx.register_tool(EchoTool)
"""


def test_discovery_does_not_run_plugin_code(tmp_path):
    root = tmp_path / "plugins"
    _write_plugin(root, "boom", "raise RuntimeError('imported')\n")

    records = _manager(tmp_path, root).discover()

    assert records["boom"].enabled is False
    assert records["boom"].status == "disabled"


def test_disabled_plugin_is_not_loaded(tmp_path):
    root = tmp_path / "plugins"
    _write_plugin(root, "boom", "raise RuntimeError('imported')\n")
    manager = _manager(tmp_path, root)

    assert manager.tool_classes() == []
    assert manager.records()[0].status == "disabled"


def test_enabled_plugin_registers_tool_and_skills(tmp_path):
    root = tmp_path / "plugins"
    plugin_dir = _write_plugin(
        root,
        "echo",
        _TOOL_PLUGIN + "    ctx.register_skills('skills')\n",
    )
    (plugin_dir / "skills" / "echo-skill").mkdir(parents=True)
    manager = _manager(tmp_path, root, enabled=["echo"])

    [record] = manager.records()

    assert record.status == "loaded", record.error
    assert [cls.name for cls in manager.tool_classes()] == ["PluginEchoTool"]
    assert manager.skill_dirs() == [("echo", (plugin_dir / "skills").resolve())]


def test_failing_register_leaves_nothing_behind(tmp_path, restore_commands):
    alias = f"/fail{uuid.uuid4().hex[:8]}"
    root = tmp_path / "plugins"
    _write_plugin(
        root,
        "half",
        _TOOL_PLUGIN
        + f"    ctx.register_command(['{alias}'])(lambda: None)\n"
        + "    raise ValueError('nope')\n",
    )
    manager = _manager(tmp_path, root, enabled=["half"])

    [record] = manager.records()

    assert record.status == "error"
    assert "nope" in record.error
    assert manager.tool_classes() == []
    assert all(alias not in meta.aliases for meta in commands_base._META)


def test_invalid_manifest_is_reported(tmp_path):
    root = tmp_path / "plugins"
    _write_plugin(root, "Bad Id", "def register(ctx): pass\n")

    [record] = _manager(tmp_path, root).discover().values()

    assert record.status == "error"
    assert "invalid manifest" in record.error


def test_newer_api_version_is_refused(tmp_path):
    root = tmp_path / "plugins"
    _write_plugin(root, "future", "def register(ctx): pass\n", api_version=99)
    manager = _manager(tmp_path, root, enabled=["future"])

    [record] = manager.records()

    assert record.status == "error"
    assert "API 99" in record.error


def test_later_directory_overrides_earlier(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    _write_plugin(first, "same", "def register(ctx): pass\n")
    override = _write_plugin(second, "same", "def register(ctx): pass\n")

    records = _manager(tmp_path, first, second).discover()

    assert records["same"].path == override


def test_set_enabled_round_trips(tmp_path):
    root = tmp_path / "plugins"
    for plugin_id in ("x", "y"):
        _write_plugin(root, plugin_id, "def register(ctx): pass\n")
    manager = _manager(tmp_path, root)
    manager.set_enabled("x", True, requested_as="x")
    manager.set_enabled("y", True)
    manager.set_enabled("x", False)

    assert manager.enabled_ids() == {"y"}
    state = json.loads(manager.state_file.read_text())
    assert state == {
        "version": 1,
        "plugins": {
            "x": {"enabled": False, "requested_by": []},
            "y": {"enabled": True, "requested_by": []},
        },
    }


def test_command_alias_clash_is_skipped(tmp_path, restore_commands):
    root = tmp_path / "plugins"
    _write_plugin(
        root,
        "clash",
        "def register(ctx):\n    ctx.register_command(['/help'])(lambda: None)\n",
    )
    manager = _manager(tmp_path, root, enabled=["clash"])

    [record] = manager.records()

    assert record.status == "loaded"
    assert record.command_names == []


def test_plugin_tool_that_shadows_a_builtin_is_dropped(monkeypatch):
    from suzent.tools import registry
    from suzent.tools.filesystem import ReadFileTool

    class Shadow(Tool):
        name = "ReadFileTool"
        tool_name = "something_else"

    class Fresh(Tool):
        name = "FreshTool"
        tool_name = "fresh"

    class FakeManager:
        def tool_classes(self):
            return [Shadow, Fresh]

    monkeypatch.setattr("suzent.plugins.get_plugin_manager", lambda: FakeManager())

    assert registry._plugin_tool_classes((ReadFileTool,)) == (Fresh,)


def test_skill_manager_includes_plugin_skills(tmp_path, monkeypatch):
    from suzent.skills import manager as skills_manager

    skills_root = tmp_path / "plugin-skills"
    skill_dir = skills_root / "hello"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: plugin-hello\ndescription: Says hello.\n---\nBody\n"
    )
    monkeypatch.setattr(
        skills_manager, "_plugin_skill_dirs", lambda: [("greeter", skills_root)]
    )

    manager = skills_manager.SkillManager(sandbox_enabled=False)
    skill = manager.loader.get_skill("plugin-hello")

    assert skill is not None
    assert skill.source == "plugin"
    assert skill.source_id == "plugin:greeter"
    assert manager.is_skill_enabled(skill.id)


def test_example_plugin_loads_and_runs(tmp_path, restore_commands):
    manager = _manager(tmp_path, EXAMPLES_DIR, enabled=["dice"])

    [record] = [r for r in manager.records() if r.id == "dice"]

    assert record.status == "loaded", record.error
    [tool_cls] = record.tool_classes
    result = tool_cls().forward(count=3, sides=6)
    assert isinstance(result, ToolResult) and result.success
    assert len(result.metadata["rolls"]) == 3
    assert record.command_names == ["/roll"]

    reply = asyncio.run(
        commands_base.dispatch(
            commands_base.CommandContext(chat_id="c", user_id="u"), "/roll 2 6"
        )
    )
    assert reply.startswith("🎲")


def test_cli_install_and_remove(tmp_path, monkeypatch):
    from suzent.cli.plugin import plugin_app

    root = tmp_path / "plugins"
    _write_plugin(root, "cli-demo", "def register(ctx): pass\n", aliases="[demo]")
    manager = _manager(tmp_path, root)
    monkeypatch.setattr("suzent.plugins.get_plugin_manager", lambda: manager)
    monkeypatch.setattr("suzent.cli.plugin._via_server", lambda action, name: None)
    runner = CliRunner()

    assert runner.invoke(plugin_app, ["install", "demo"]).exit_code == 0
    assert manager.enabled_ids() == {"cli-demo"}
    listing = runner.invoke(plugin_app, ["list"])
    assert "[ON ]  cli-demo (demo)" in listing.output
    assert runner.invoke(plugin_app, ["install", "missing"]).exit_code == 1
    assert runner.invoke(plugin_app, ["remove", "cli-demo"]).exit_code == 0
    assert manager.enabled_ids() == set()


def test_cli_hands_changes_to_a_running_server(tmp_path, monkeypatch):
    from suzent.cli.plugin import plugin_app

    root = tmp_path / "plugins"
    _write_plugin(root, "cli-demo", "def register(ctx): pass\n")
    manager = _manager(tmp_path, root)
    monkeypatch.setattr("suzent.plugins.get_plugin_manager", lambda: manager)
    calls = []

    class FakePlugins:
        async def install(self, name):
            calls.append(("install", name))
            return {"id": name}

        async def remove(self, name):
            calls.append(("remove", name))
            return {"id": name}

    class FakeClient:
        plugins = FakePlugins()

        async def aclose(self):
            pass

    monkeypatch.setattr("suzent.client.get_client", lambda: FakeClient())
    runner = CliRunner()

    installed = runner.invoke(plugin_app, ["install", "cli-demo"])
    removed = runner.invoke(plugin_app, ["remove", "cli-demo"])

    assert "active in the running server" in installed.output
    assert "unloaded it" in removed.output
    assert calls == [("install", "cli-demo"), ("remove", "cli-demo")]
    # The server owns the change; the CLI did not write state itself.
    assert manager.enabled_ids() == set()


def test_plugins_load_and_unload_without_a_restart(
    tmp_path, monkeypatch, restore_commands
):
    from suzent.plugins import manager as plugin_manager
    from suzent.tools import registry

    root = tmp_path / "plugins"
    _write_plugin(
        root,
        "hot",
        _TOOL_PLUGIN
        + textwrap.dedent(
            """
            _register_tool = register


            def register(ctx):
                _register_tool(ctx)

                @ctx.register_command(["/hotcmd"], description="hot")
                def hot_cmd():
                    async def _impl():
                        return "hot!"

                    return _impl
            """
        ),
    )
    manager = _manager(tmp_path, root)
    monkeypatch.setattr(plugin_manager, "_manager", manager)
    manager.load()
    registry.reset_tool_caches()

    def runtime_names():
        return {cls.tool_name for cls in registry._all_tool_classes()}

    def run(text):
        return asyncio.run(
            commands_base.dispatch(
                commands_base.CommandContext(chat_id="c", user_id="u"), text
            )
        )

    assert "plugin_echo" not in runtime_names()

    manager.set_enabled("hot", True)
    record = manager.activate("hot")

    assert record.status == "loaded", record.error
    assert "plugin_echo" in runtime_names()
    assert registry.get_tool_class_name("plugin_echo") == "PluginEchoTool"
    assert run("/hotcmd") == "hot!"

    manager.set_enabled("hot", False)
    manager.deactivate("hot")

    assert "plugin_echo" not in runtime_names()
    assert run("/hotcmd") is None
    assert not any(m.aliases == ["/hotcmd"] for m in commands_base._META)
    registry.reset_tool_caches()
