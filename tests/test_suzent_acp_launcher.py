"""Tests for the standalone ``suzent-acp`` launcher package."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "packages" / "suzent-acp" / "src"
sys.path.insert(0, str(PACKAGE_SRC))

from suzent_acp.fallback import (  # noqa: E402
    AGENT_AUTH_ID,
    INTERNAL_ERROR,
    METHOD_NOT_FOUND,
    TERMINAL_AUTH_ID,
    respond,
    serve,
)
from suzent_acp.launcher import find_suzent, workspace_candidates  # noqa: E402

from suzent.acp.server import ACPAgentServer  # noqa: E402


def _make_cli(workspace: Path, windows: bool = False) -> Path:
    cli = (
        workspace / ".venv" / "Scripts" / "suzent.exe"
        if windows
        else workspace / ".venv" / "bin" / "suzent"
    )
    cli.parent.mkdir(parents=True)
    cli.write_text("")
    return cli


def test_finds_default_workspace(tmp_path: Path) -> None:
    cli = _make_cli(tmp_path / "suzent")
    assert find_suzent({"PATH": ""}, tmp_path, windows=False) == str(cli)


def test_installer_marker_wins_over_default(tmp_path: Path) -> None:
    _make_cli(tmp_path / "suzent")
    chosen = tmp_path / "elsewhere"
    cli = _make_cli(chosen, windows=True)
    (tmp_path / ".suzent").mkdir()
    (tmp_path / ".suzent" / "install-dir.txt").write_text(f"{chosen}\n")
    assert find_suzent({"PATH": ""}, tmp_path, windows=True) == str(cli)


def test_env_override_comes_first(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "install-dir.txt").write_text(str(tmp_path / "marker"))
    env = {"SUZENT_DIR": str(tmp_path / "env"), "SUZENT_DATA_DIR": str(data)}
    assert workspace_candidates(env, tmp_path) == [
        tmp_path / "env",
        tmp_path / "marker",
        tmp_path / "suzent",
    ]


def test_relative_marker_is_ignored(tmp_path: Path) -> None:
    (tmp_path / ".suzent").mkdir()
    (tmp_path / ".suzent" / "install-dir.txt").write_text("relative/dir")
    assert workspace_candidates({}, tmp_path) == [tmp_path / "suzent"]


def test_falls_back_to_path(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cli = bin_dir / "suzent"
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o755)
    found = find_suzent({"PATH": str(bin_dir)}, tmp_path / "home", windows=False)
    assert found == str(cli)


def test_not_installed(tmp_path: Path) -> None:
    assert find_suzent({"PATH": ""}, tmp_path, windows=False) is None


@pytest.mark.parametrize("terminal", [False, True])
async def test_fallback_matches_installed_auth_methods(terminal: bool) -> None:
    params = {
        "protocolVersion": 1,
        "clientCapabilities": {"auth": {"terminal": terminal}},
        "clientInfo": {"name": "Zed"},
    }
    replies: list[dict] = []

    async def send(message: dict) -> None:
        replies.append(message)

    server = ACPAgentServer(object(), send, require_auth=True)  # type: ignore[arg-type]
    await server.dispatch(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": params}
    )
    installed = replies[0]["result"]["authMethods"]

    fallback = respond(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": params}
    )
    assert fallback is not None
    assert fallback["result"]["authMethods"] == installed
    ids = [method["id"] for method in installed]
    assert ids == ([TERMINAL_AUTH_ID] if terminal else []) + [AGENT_AUTH_ID]


def test_fallback_explains_install_and_ignores_notifications() -> None:
    session = respond(
        {"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {}}
    )
    assert session is not None
    assert session["error"]["code"] == INTERNAL_ERROR
    assert "https://suzent.com" in session["error"]["message"]

    unknown = respond({"jsonrpc": "2.0", "id": 3, "method": "nope"})
    assert unknown is not None and unknown["error"]["code"] == METHOD_NOT_FOUND
    assert respond({"jsonrpc": "2.0", "method": "session/cancel"}) is None


def test_fallback_serve_skips_garbage() -> None:
    lines = iter(
        [
            "not json\n",
            "\n",
            json.dumps({"jsonrpc": "2.0", "id": 7, "method": "initialize"}) + "\n",
            "",
        ]
    )
    written: list[str] = []
    serve(lambda: next(lines), written.append)
    assert len(written) == 1
    assert json.loads(written[0])["id"] == 7


def test_module_answers_handshake_without_suzent(tmp_path: Path) -> None:
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": 1, "clientCapabilities": {}},
    }
    result = subprocess.run(
        [sys.executable, "-m", "suzent_acp"],
        input=json.dumps(request) + "\n",
        capture_output=True,
        text=True,
        timeout=30,
        env={
            "HOME": str(tmp_path),
            "USERPROFILE": str(tmp_path),
            "PATH": "",
            "PYTHONPATH": str(PACKAGE_SRC),
        },
        check=True,
    )
    reply = json.loads(result.stdout)
    assert reply["result"]["authMethods"][0]["id"] == AGENT_AUTH_ID
    assert "not installed" in result.stderr
