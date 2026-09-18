"""Tests for the automatic web UI rebuild."""

from __future__ import annotations

import os
import sys
import time

import pytest

from suzent import webui_build


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """A fake source checkout with a frontend, a builder and a staged bundle."""
    frontend = tmp_path / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "package.json").write_text("{}", encoding="utf-8")
    (frontend / "src" / "main.tsx").write_text("// source", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "build_webui.py").write_text("", encoding="utf-8")

    bundle = tmp_path / "webui"
    bundle.mkdir()
    index = bundle / "index.html"
    index.write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr(webui_build, "_project_root", lambda: tmp_path)
    monkeypatch.setattr("suzent.webui.INDEX_FILE", index)
    monkeypatch.setattr(webui_build.shutil, "which", lambda _name: "/usr/bin/npm")
    # The guard that keeps a real test suite out of npm would otherwise disable
    # everything under test here; monkeypatch puts it back afterwards.
    monkeypatch.delitem(sys.modules, "pytest")

    webui_build._building = False
    webui_build._last_checked_at = 0.0
    webui_build._last_failure_mtime = None
    return tmp_path


def _touch_source(checkout, offset_seconds: float = 10.0) -> float:
    """Make the frontend look newer than the bundle."""
    source = checkout / "frontend" / "src" / "main.tsx"
    when = time.time() + offset_seconds
    os.utime(source, (when, when))
    return when


def test_installed_wheel_has_nothing_to_build(tmp_path, monkeypatch):
    # No frontend/ next to the package: the bundle shipped prebuilt and there is
    # no source to compare it against.
    monkeypatch.setattr(webui_build, "_project_root", lambda: tmp_path)
    assert webui_build.auto_build_enabled() is False
    assert webui_build.bundle_is_stale() is False
    assert webui_build.rebuild_if_stale() is False


def test_disabled_by_environment(checkout, monkeypatch):
    monkeypatch.setenv("SUZENT_AUTO_BUILD_WEBUI", "0")
    _touch_source(checkout)
    assert webui_build.auto_build_enabled() is False
    assert webui_build.rebuild_if_stale() is False


def test_missing_npm_is_not_an_error(checkout, monkeypatch):
    monkeypatch.setattr(webui_build.shutil, "which", lambda _name: None)
    _touch_source(checkout)
    assert webui_build.auto_build_enabled() is False
    assert webui_build.rebuild_if_stale() is False


def test_fresh_bundle_is_not_rebuilt(checkout):
    assert webui_build.bundle_is_stale() is False
    assert webui_build.rebuild_if_stale() is False


def test_edited_source_makes_the_bundle_stale(checkout):
    _touch_source(checkout)
    assert webui_build.bundle_is_stale() is True


def test_ignored_directories_do_not_count_as_source(checkout):
    # node_modules and dist churn constantly; treating them as inputs would mean
    # the bundle is permanently stale.
    for name in ("node_modules", "dist"):
        directory = checkout / "frontend" / name
        directory.mkdir()
        output = directory / "whatever.js"
        output.write_text("", encoding="utf-8")
        when = time.time() + 30
        os.utime(output, (when, when))
    assert webui_build.bundle_is_stale() is False


def test_missing_bundle_counts_as_stale(checkout, monkeypatch):
    (checkout / "webui" / "index.html").unlink()
    assert webui_build.bundle_is_stale() is True


def test_rebuild_runs_the_builder_script(checkout, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return _completed(0)

    monkeypatch.setattr(webui_build.subprocess, "run", fake_run)
    _touch_source(checkout)

    assert webui_build.rebuild_if_stale() is True
    _settle()
    assert len(calls) == 1
    assert calls[0][0] == sys.executable
    assert calls[0][1].endswith("build_webui.py")
    assert webui_build._building is False


def test_a_second_call_does_not_start_a_second_build(checkout, monkeypatch):
    started = 0

    def fake_run(command, **kwargs):
        nonlocal started
        started += 1
        time.sleep(0.2)
        return _completed(0)

    monkeypatch.setattr(webui_build.subprocess, "run", fake_run)
    _touch_source(checkout)

    assert webui_build.rebuild_if_stale() is True
    webui_build._last_checked_at = 0.0  # defeat the scan cooldown, not the lock
    assert webui_build.rebuild_if_stale() is False
    _settle(0.5)
    assert started == 1


def test_a_failed_build_is_not_retried_until_the_source_changes(checkout, monkeypatch):
    attempts = 0

    def fake_run(command, **kwargs):
        nonlocal attempts
        attempts += 1
        return _completed(1, stderr="error TS1005: ';' expected")

    monkeypatch.setattr(webui_build.subprocess, "run", fake_run)
    _touch_source(checkout)

    assert webui_build.rebuild_if_stale() is True
    _settle()
    assert attempts == 1

    # Same broken source: retrying on every page load would spin npm forever.
    webui_build._last_checked_at = 0.0
    assert webui_build.rebuild_if_stale() is False
    assert attempts == 1

    # An edit is a new attempt, because it might be the fix.
    _touch_source(checkout, offset_seconds=60)
    webui_build._last_checked_at = 0.0
    assert webui_build.rebuild_if_stale() is True
    _settle()
    assert attempts == 2


def test_scan_is_rate_limited(checkout, monkeypatch):
    monkeypatch.setattr(webui_build.subprocess, "run", lambda *a, **k: _completed(0))
    scans = 0
    real_scan = webui_build._newest_source_mtime

    def counting_scan(frontend):
        nonlocal scans
        scans += 1
        return real_scan(frontend)

    monkeypatch.setattr(webui_build, "_newest_source_mtime", counting_scan)

    assert webui_build.rebuild_if_stale() is False
    before = scans
    assert webui_build.rebuild_if_stale() is False
    assert scans == before


class _completed:
    """Minimal stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _settle(timeout: float = 2.0) -> None:
    """Wait for the rebuild thread to finish."""
    deadline = time.monotonic() + timeout
    while webui_build._building and time.monotonic() < deadline:
        time.sleep(0.01)
