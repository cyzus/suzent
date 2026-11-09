"""Desktop computer-use: argv mapping, JSON envelopes, and a mocked CLI."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from suzent.plugins.binaries import PluginBinary
from suzent.plugins.manager import PluginManager
from suzent.plugins.manifest import PluginManifest
from suzent.tools.base import ToolErrorCode

REPO = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO / "plugins" / "desktop"


def _import_plugin() -> None:
    """Import the plugin package the way the plugin manager does."""
    name = "suzent_plugin_desktop"
    if name in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(
        name, PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(PLUGIN_DIR)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


_import_plugin()
catalog = importlib.import_module("suzent_plugin_desktop.catalog")
runner = importlib.import_module("suzent_plugin_desktop.runner")
DesktopTool = importlib.import_module("suzent_plugin_desktop.tool").DesktopTool
prepare_call = catalog.prepare_call
INSTALL_HINT = runner.INSTALL_HINT
parse_envelope = runner.parse_envelope
render_envelope = runner.render_envelope
reset_binary_cache = runner.reset_binary_cache
resolve_binary = runner.resolve_binary
SPEC = PluginManifest.from_file(PLUGIN_DIR / "plugin.yaml").binaries[0]


@pytest.fixture(autouse=True)
def _plugin_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("suzent.config.paths.DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(runner, "_binary", PluginBinary("desktop", SPEC))


REF = "@s8f3k2p9:e8"


def test_snapshot_argv_uses_cli_flags() -> None:
    prepared = prepare_call(
        "snapshot",
        {"app": "Finder", "interactive_only": True, "compact": True},
    )

    assert prepared.readonly is True
    assert prepared.argv == [
        "snapshot",
        "--app",
        "Finder",
        "--interactive-only",
        "--compact",
    ]


def test_headed_click_puts_the_global_flag_first() -> None:
    prepared = prepare_call(
        "click",
        {"ref": REF},
        headed=True,
        session="run-1",
    )

    assert prepared.readonly is False
    assert prepared.argv == ["--headed", "--session", "run-1", "click", REF]


def test_type_keeps_text_as_one_argument() -> None:
    prepared = prepare_call("type", {"ref": REF, "text": "hello world"})

    assert prepared.argv == ["type", REF, "hello world"]


def test_negative_coordinates_use_equals_form() -> None:
    prepared = prepare_call("mouse-move", {"xy": "-10,20"}, headed=True)

    assert prepared.argv == ["--headed", "mouse-move", "--xy=-10,20"]


def test_launch_args_that_look_like_flags_are_not_split() -> None:
    prepared = prepare_call(
        "launch",
        {"app": "Firefox", "launch_args": ["--new-tab"], "env": ["LANG=C"]},
    )

    assert prepared.argv == [
        "launch",
        "--arg=--new-tab",
        "--env",
        "LANG=C",
        "Firefox",
    ]


def test_hyphenated_text_is_passed_after_end_of_flags() -> None:
    prepared = prepare_call("type", {"ref": REF, "text": "--help"})

    assert prepared.argv == ["type", "--", REF, "--help"]


def test_bare_ref_is_rejected() -> None:
    with pytest.raises(ValueError, match="qualified ref"):
        prepare_call("click", {"ref": "@e8"})


def test_unknown_command_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown desktop command"):
        prepare_call("rm", {})


def test_held_input_is_rejected_before_it_can_run() -> None:
    with pytest.raises(ValueError, match="press"):
        prepare_call("key-down", {"combo": "a"})


def test_batch_rejects_commands_outside_the_allowlist() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        prepare_call(
            "batch", {"entries": [{"command": "trace", "args": {"action": "show"}}]}
        )


def test_read_batch_stays_read_only() -> None:
    prepared = prepare_call(
        "batch",
        {
            "entries": [
                {"command": "version"},
                {"command": "skills", "args": {"action": "get"}},
            ]
        },
    )

    assert prepared.readonly is True
    payload = json.loads(prepared.argv[-1])
    assert payload[0]["command"] == "version"


def test_screenshot_path_is_not_read_only() -> None:
    assert prepare_call("screenshot", {"screen": 0}).readonly is True
    assert prepare_call("screenshot", {"path": "/tmp/screen.png"}).readonly is False


def test_permissions_guide_is_not_read_only() -> None:
    assert prepare_call("permissions").readonly is True
    assert prepare_call("permissions", {"guide": True}).readonly is False


def test_session_list_is_read_only_and_headed_notifications_are_not() -> None:
    assert prepare_call("session", {"subcommand": "list"}).readonly is True
    assert prepare_call("session", {"subcommand": "gc"}).readonly is False
    assert prepare_call("list-notifications").readonly is True
    assert prepare_call("list-notifications", headed=True).readonly is False


def test_unused_option_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not use"):
        prepare_call("click", {"ref": REF, "text": "nope"})


def test_render_envelope_failure_without_disposition_stays_short() -> None:
    rendered = render_envelope(
        {"ok": False, "command": "open-system-surface", "error": {"code": "INTERNAL"}}
    )

    first_line = rendered.message.splitlines()[0]
    assert first_line == "agent-desktop open-system-surface failed: INTERNAL."
    assert "retry=" not in rendered.message
    assert "Docker sandbox" not in rendered.message


def test_render_envelope_surfaces_retry_and_drops_image_bytes() -> None:
    rendered = render_envelope(
        {
            "version": "2.5",
            "ok": False,
            "command": "click",
            "error": {
                "code": "STALE_REF",
                "message": "ref is gone",
                "suggestion": "Re-run a snapshot",
                "disposition": {"delivery": "not_delivered", "retry": "safe"},
            },
        }
    )

    assert rendered.ok is False
    assert "STALE_REF" in rendered.message
    assert "retry=safe" in rendered.message
    assert "Re-run a snapshot" in rendered.message

    image = render_envelope(
        {
            "ok": True,
            "command": "screenshot",
            "data": {"format": "png", "data": "A" * 400},
        }
    )
    assert "AAAA" not in image.message
    assert "omitted" in image.message


def test_parse_envelope_rejects_plain_text() -> None:
    with pytest.raises(ValueError, match="JSON"):
        parse_envelope("not json")


def test_missing_binary_explains_how_to_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SUZENT_AGENT_DESKTOP_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda _name: None)

    with pytest.raises(
        runner.DesktopBinaryError, match="suzent plugin install desktop"
    ):
        resolve_binary()
    assert "unsigned" in INSTALL_HINT
    assert "permissions --guide" in INSTALL_HINT


def test_binary_override_must_be_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = tmp_path / "agent-desktop"
    monkeypatch.setenv("SUZENT_AGENT_DESKTOP_BIN", str(missing))

    with pytest.raises(runner.DesktopBinaryError, match="SUZENT_AGENT_DESKTOP_BIN"):
        resolve_binary()


@pytest.mark.asyncio
async def test_run_cli_kills_a_process_whose_task_is_cancelled(tmp_path: Path) -> None:
    """A cancelled desktop call must not leave the host process running.

    The child writes a marker only after a delay. Cancelling the task before
    that delay has to kill it; otherwise the marker appears with nobody watching.
    """
    started = tmp_path / "started"
    finished = tmp_path / "finished"
    script = tmp_path / "delayed.py"
    script.write_text(
        "import pathlib, sys, time\n"
        "pathlib.Path(sys.argv[1]).write_text('started')\n"
        "time.sleep(2)\n"
        "pathlib.Path(sys.argv[2]).write_text('finished')\n",
        encoding="utf-8",
    )
    task = asyncio.create_task(
        runner.run_cli(
            sys.executable,
            [str(script), str(started), str(finished)],
            timeout=30,
        )
    )
    for _ in range(50):
        if started.exists():
            break
        await asyncio.sleep(0.05)
    else:
        task.cancel()
        raise AssertionError("the child never started")

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(2.5)

    assert not finished.exists()


@pytest.mark.asyncio
async def test_run_cli_execs_the_host_binary_without_a_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict = {}

    class FakeProcess:
        def __init__(self) -> None:
            self.returncode = None
            self.pid = 424242

        async def communicate(self) -> tuple[bytes, bytes]:
            self.returncode = 0
            body = json.dumps(
                {"ok": True, "command": "version", "data": {"version": "1.0.2"}}
            )
            return body.encode(), b""

        def kill(self) -> None:
            self.returncode = -9

        async def wait(self) -> int:
            return self.returncode or 0

    async def fake_exec(*args: object, **kwargs: object) -> FakeProcess:
        seen["args"] = args
        seen["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(runner.asyncio, "create_subprocess_exec", fake_exec)

    code, stdout, _stderr = await runner.run_cli(
        "/usr/local/bin/agent-desktop", ["version"], timeout=5
    )

    assert code == 0
    assert json.loads(stdout)["data"]["version"] == "1.0.2"
    assert seen["args"][0] == "/usr/local/bin/agent-desktop"
    assert seen["args"][1:] == ("version",)
    assert "shell" not in seen["kwargs"]
    assert seen["kwargs"]["stdin"] is runner.asyncio.subprocess.DEVNULL


def _ctx(*, sandbox: bool = False) -> SimpleNamespace:
    return SimpleNamespace(deps=SimpleNamespace(sandbox_enabled=sandbox))


@pytest.fixture
def fake_cli(monkeypatch: pytest.MonkeyPatch):
    reset_binary_cache()
    calls: list[list[str]] = []

    async def fake_run(
        binary: str, argv: list[str], *, timeout: float
    ) -> tuple[int, str, str]:
        calls.append(argv)
        if argv == ["version"]:
            body = {
                "ok": True,
                "command": "version",
                "data": {"version": "1.0.2", "os": "linux", "target": "x86_64"},
            }
            return 0, json.dumps(body), ""
        body = {
            "version": "2.5",
            "ok": True,
            "command": argv[-1] if argv else "",
            "data": {"app": "Finder", "complete": True, "tree": {"role": "window"}},
        }
        return 0, json.dumps(body), ""

    monkeypatch.setattr(runner, "resolve_binary", lambda: "/usr/bin/agent-desktop")
    monkeypatch.setattr(runner, "run_cli", fake_run)
    yield calls
    reset_binary_cache()


@pytest.mark.asyncio
async def test_tool_parses_a_snapshot_and_checks_the_cli_version(fake_cli) -> None:
    result = await DesktopTool().forward(
        _ctx(sandbox=True),
        "snapshot",
        catalog.DesktopOptions(app="Finder", interactive_only=True),
    )

    assert result.success
    assert "Finder" in result.message
    assert result.metadata["host_execution"] is True
    assert fake_cli[0] == ["version"]
    assert fake_cli[1] == ["snapshot", "--app", "Finder", "--interactive-only"]


@pytest.mark.asyncio
async def test_tool_does_not_launch_the_cli_when_it_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_calls: list[str] = []

    def explode() -> str:
        raise runner.DesktopBinaryError(INSTALL_HINT)

    def refuse_install(*_args: object, **_kwargs: object) -> None:
        install_calls.append("install")
        raise AssertionError("tool calls must not download agent-desktop")

    monkeypatch.setattr("suzent.plugins.binaries.install", refuse_install)

    async def fail_run(*_args: object, **_kwargs: object) -> tuple[int, str, str]:
        raise AssertionError("the CLI must not be started when it is not installed")

    monkeypatch.setattr(runner, "resolve_binary", explode)
    monkeypatch.setattr(runner, "run_cli", fail_run)

    result = await DesktopTool().forward(_ctx(), "version", None)

    assert result.success is False
    assert result.error_code == ToolErrorCode.EXECUTION_FAILED
    assert "suzent plugin install desktop" in result.message
    assert "unsigned" in result.message
    assert install_calls == []


@pytest.mark.asyncio
async def test_tool_rejects_a_different_major_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_binary_cache()

    async def wrong_version(
        _binary: str, argv: list[str], *, timeout: float
    ) -> tuple[int, str, str]:
        assert argv == ["version"]
        body = {"ok": True, "command": "version", "data": {"version": "2.0.0"}}
        return 0, json.dumps(body), ""

    monkeypatch.setattr(runner, "resolve_binary", lambda: "/usr/bin/agent-desktop")
    monkeypatch.setattr(runner, "run_cli", wrong_version)

    result = await DesktopTool().forward(_ctx(), "status", None)

    assert result.success is False
    assert "1.0.x" in result.message
    assert "2.0.0" in result.message
    reset_binary_cache()


@pytest.mark.asyncio
async def test_tool_reports_a_stale_ref_from_the_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_binary_cache()

    async def fake_run(
        _binary: str, argv: list[str], *, timeout: float
    ) -> tuple[int, str, str]:
        if argv == ["version"]:
            return (
                0,
                json.dumps(
                    {"ok": True, "command": "version", "data": {"version": "1.0.2"}}
                ),
                "",
            )
        body = {
            "ok": False,
            "command": "click",
            "error": {
                "code": "STALE_REF",
                "message": "gone",
                "suggestion": "Re-run a snapshot",
                "disposition": {"delivery": "not_delivered", "retry": "safe"},
            },
        }
        return 1, json.dumps(body), ""

    monkeypatch.setattr(runner, "resolve_binary", lambda: "/usr/bin/agent-desktop")
    monkeypatch.setattr(runner, "run_cli", fake_run)

    result = await DesktopTool().forward(
        _ctx(), "click", catalog.DesktopOptions(ref=REF)
    )

    assert result.success is False
    assert result.error_code == ToolErrorCode.EXECUTION_FAILED
    assert "STALE_REF" in result.message
    assert "retry=safe" in result.message
    reset_binary_cache()


@pytest.mark.asyncio
async def test_tool_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_binary_cache()

    async def fake_run(
        _binary: str, argv: list[str], *, timeout: float
    ) -> tuple[int, str, str]:
        if argv == ["version"]:
            return (
                0,
                json.dumps(
                    {"ok": True, "command": "version", "data": {"version": "1.0.0"}}
                ),
                "",
            )
        raise runner.DesktopTimeout("agent-desktop wait did not finish within 15s")

    monkeypatch.setattr(runner, "resolve_binary", lambda: "/usr/bin/agent-desktop")
    monkeypatch.setattr(runner, "run_cli", fake_run)

    result = await DesktopTool().forward(_ctx(), "wait", catalog.DesktopOptions(ms=10))

    assert result.error_code == ToolErrorCode.TIMEOUT
    reset_binary_cache()


def test_desktop_plugin_stays_off_until_installed(tmp_path: Path) -> None:
    manager = PluginManager(
        [],
        tmp_path / "plugins.json",
        builtin_dirs=[REPO / "plugins"],
        entry_point_group=None,
    )

    record = manager.discover()["desktop"]

    assert record.manifest.default_enabled is False
    assert record.enabled is False
    assert manager.tool_classes() == []


def test_enabled_desktop_plugin_registers_the_tool_and_skill(tmp_path: Path) -> None:
    state = tmp_path / "plugins.json"
    state.write_text(
        json.dumps({"version": 1, "plugins": {"desktop": {"enabled": True}}})
    )
    manager = PluginManager(
        [],
        state,
        builtin_dirs=[REPO / "plugins"],
        entry_point_group=None,
    )

    record = next(item for item in manager.records() if item.id == "desktop")

    assert record.status == "loaded", record.error
    assert [cls.tool_name for cls in record.tool_classes] == ["desktop"]
    assert record.tool_classes[0].requires_approval is True
    skill_dirs = [
        path for plugin_id, path in manager.skill_dirs() if plugin_id == "desktop"
    ]
    assert skill_dirs
    assert (skill_dirs[0] / "suzent-desktop" / "SKILL.md").is_file()


def test_desktop_reads_are_read_only_and_side_effects_are_not() -> None:
    reads = [
        {"command": "snapshot", "options": {"app": "Finder", "interactive_only": True}},
        {
            "command": "batch",
            "options": {
                "entries": [
                    {"command": "version"},
                    {"command": "snapshot", "args": {"app": "Finder"}},
                ]
            },
        },
    ]
    writes = [
        {"command": "click", "options": {"ref": REF}},
        {"command": "list-notifications", "headed": True},
        {"command": "permissions", "options": {"guide": True}},
        {"command": "screenshot", "options": {"path": "/tmp/screen.png"}},
        {"command": "session", "options": {"subcommand": "start"}},
        {
            "command": "batch",
            "options": {
                "entries": [{"command": "click", "args": {"ref_id": "@s8f3k2p9:e1"}}]
            },
        },
    ]
    assert all(DesktopTool.is_readonly_call(args) for args in reads)
    assert not any(DesktopTool.is_readonly_call(args) for args in writes)


def test_desktop_approval_is_remembered_per_command() -> None:
    remember = DesktopTool.remember_as({"command": "click", "options": {"ref": REF}})

    assert remember.match == {"command": "click"}
    assert remember.label == "desktop click"
    assert DesktopTool.remember_as({}).match is None


def test_desktop_refuses_a_bare_ref_before_approval() -> None:
    reason = DesktopTool.invalid_call_reason(
        {"command": "click", "options": {"ref": "@e8"}}
    )

    assert reason is not None and "@s8f3k2p9:e8" in reason
    assert DesktopTool.invalid_call_reason({"command": "snapshot"}) is None


def test_desktop_plugin_pins_every_platform_to_the_npm_tarball() -> None:
    assert SPEC.package == "agent-desktop"
    assert SPEC.version == "1.0.2"
    assert set(SPEC.platforms) == {
        "darwin-arm64",
        "darwin-x64",
        "linux-arm64",
        "linux-x64",
        "win32-arm64",
        "win32-x64",
    }
    assert "agent-desktop-macos-helper" in SPEC.platforms["darwin-arm64"].files
    assert SPEC.after_install == {"darwin": ["permissions", "--guide"]}
