import base64
import subprocess
from pathlib import Path

import pytest

from suzent.sync import git_transport
from suzent.sync.git_transport import github_auth_env, redact_git_credentials, run_git


def test_run_git_redacts_token_in_errors(tmp_path: Path, monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="",
            stderr=(
                "To https://x-access-token:TOKEN_VALUE@github.com/alice/brain.git\n"
                "! [rejected] main -> main"
            ),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        run_git(tmp_path, "push", "origin", "main", token="TOKEN_VALUE")

    message = str(exc_info.value)
    assert "TOKEN_VALUE" not in message
    assert "https://<redacted>@github.com/alice/brain.git" in message


def test_token_goes_in_env_not_argv(tmp_path: Path, monkeypatch):
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="ok")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.delenv("GIT_CONFIG_COUNT", raising=False)

    run_git(tmp_path, "fetch", "origin", "main", token="TOKEN_VALUE")

    assert not any("TOKEN_VALUE" in arg for arg in captured["argv"])
    env = captured["env"]
    assert env["GIT_CONFIG_COUNT"] == "1"
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    expected = base64.b64encode(b"x-access-token:TOKEN_VALUE").decode()
    assert env["GIT_CONFIG_VALUE_0"] == f"AUTHORIZATION: basic {expected}"
    assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_auth_env_appends_to_existing_git_config_env(monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.autocrlf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")

    env = github_auth_env("tok")

    assert env["GIT_CONFIG_COUNT"] == "2"
    assert env["GIT_CONFIG_KEY_0"] == "core.autocrlf"
    assert env["GIT_CONFIG_KEY_1"] == "http.https://github.com/.extraheader"


def test_run_git_without_token_inherits_env(tmp_path: Path, monkeypatch):
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="")

    monkeypatch.setattr(git_transport.subprocess, "run", fake_run)
    run_git(tmp_path, "status")
    assert captured["env"] is None


def test_redact_auth_header():
    assert "SECRET" not in redact_git_credentials("AUTHORIZATION: basic SECRET")
