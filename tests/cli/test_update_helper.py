"""Tests for the detached Windows update helper."""

import importlib
import subprocess
import sys


update_helper = importlib.import_module("suzent.cli.update_helper")


def test_update_helper_waits_then_runs_cli_module(monkeypatch, tmp_path):
    events = []

    def fake_run(command, **kwargs):
        events.append(("run", command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        update_helper,
        "_wait_for_process_exit",
        lambda pid: events.append(("wait", pid)),
    )
    monkeypatch.setattr(update_helper.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_helper",
            "--wait-pid",
            "4321",
            "--root",
            str(tmp_path),
            "--dev",
        ],
    )

    assert update_helper.main() == 0
    assert events[0] == ("wait", 4321)
    _, command, kwargs = events[1]
    assert command == [sys.executable, "-m", "suzent.cli", "update", "--dev"]
    assert kwargs["cwd"] == tmp_path
