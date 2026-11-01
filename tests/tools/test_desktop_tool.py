"""Desktop computer-use: argv mapping, JSON envelopes, and a mocked CLI."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from suzent.plugins.manager import PluginManager
from suzent.tools.base import ToolErrorCode
from suzent.tools.desktop import catalog, runner
from suzent.tools.desktop.catalog import prepare_call
from suzent.tools.desktop.runner import (
    INSTALL_HINT,
    parse_envelope,
    render_envelope,
    reset_binary_cache,
    resolve_binary,
)
from suzent.tools.desktop.tool import DesktopTool

REPO = Path(__file__).resolve().parents[2]
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
    monkeypatch.setattr(runner.shutil, "which", lambda _name: None)

    with pytest.raises(runner.DesktopBinaryError, match="npm install -g agent-desktop"):
        resolve_binary()
    assert "github.com/vercel-labs/agent-desktop/releases" in INSTALL_HINT
    assert "permissions --guide" in INSTALL_HINT


def test_binary_override_must_be_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = tmp_path / "agent-desktop"
    monkeypatch.setenv("SUZENT_AGENT_DESKTOP_BIN", str(missing))

    with pytest.raises(runner.DesktopBinaryError, match="SUZENT_AGENT_DESKTOP_BIN"):
        resolve_binary()


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
    assert "Docker sandbox" in result.message
    assert result.metadata["host_execution"] is True
    assert fake_cli[0] == ["version"]
    assert fake_cli[1] == ["snapshot", "--app", "Finder", "--interactive-only"]


@pytest.mark.asyncio
async def test_tool_does_not_launch_the_cli_when_it_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode() -> str:
        raise runner.DesktopBinaryError(INSTALL_HINT)

    async def fail_run(*_args: object, **_kwargs: object) -> tuple[int, str, str]:
        raise AssertionError("the CLI must not be started when it is not installed")

    monkeypatch.setattr(runner, "resolve_binary", explode)
    monkeypatch.setattr(runner, "run_cli", fail_run)

    result = await DesktopTool().forward(_ctx(), "version", None)

    assert result.success is False
    assert result.error_code == ToolErrorCode.EXECUTION_FAILED
    assert "npm install -g agent-desktop" in result.message
    assert "does not install" in result.message


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
