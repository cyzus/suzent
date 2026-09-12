"""Tests for the shared launcher-shortcut implementation."""

import json
import plistlib
import subprocess
from pathlib import Path

import pytest

from suzent.cli import shortcuts


@pytest.fixture(autouse=True)
def offline_helpers(monkeypatch):
    """Keep desktop-database, icon-cache and Launch Services calls out of tests."""
    monkeypatch.setattr(shortcuts, "_run", lambda command: None)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A bootstrapped workspace with an isolated HOME to write shortcuts into."""
    home = tmp_path / "home"
    (home / "Desktop").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    root = tmp_path / "suzent"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "suzent-ui").write_text("#!/bin/sh\n", encoding="utf-8")
    (root / ".suzent").mkdir()
    (root / ".suzent" / "release-tag").write_text("v1.2.3", encoding="utf-8")
    return root


@pytest.fixture
def linux(monkeypatch):
    monkeypatch.setattr(shortcuts, "IS_WINDOWS", False)
    monkeypatch.setattr(shortcuts, "IS_MACOS", False)
    monkeypatch.setattr(shortcuts, "_DESKTOP_DEFAULT", False)


@pytest.fixture
def macos(monkeypatch):
    monkeypatch.setattr(shortcuts, "IS_WINDOWS", False)
    monkeypatch.setattr(shortcuts, "IS_MACOS", True)
    monkeypatch.setattr(shortcuts, "_DESKTOP_DEFAULT", False)


def _applications(home):
    return home / ".local" / "share" / "applications"


def test_linux_install_writes_menu_entry_and_manifest(workspace, linux, tmp_path):
    report = shortcuts.install_or_repair(workspace)

    entry = _applications(tmp_path / "home") / "com.suzent.app.desktop"
    assert report.ok
    assert report.created == [str(entry)]
    content = entry.read_text(encoding="utf-8")
    assert f'Exec="{workspace / "bin" / "suzent-ui"}"' in content
    assert f"Path={workspace}" in content

    manifest = json.loads(
        (workspace / ".suzent" / "shortcuts.json").read_text(encoding="utf-8")
    )
    assert manifest["schema"] == shortcuts.MANIFEST_VERSION
    assert manifest["options"] == {"application_menu": True, "desktop": False}
    assert [item["kind"] for item in manifest["entries"]] == ["application_menu"]


def test_repeated_repair_leaves_a_correct_entry_untouched(workspace, linux, tmp_path):
    shortcuts.install_or_repair(workspace)
    report = shortcuts.install_or_repair(workspace)

    entry = _applications(tmp_path / "home") / "com.suzent.app.desktop"
    assert report.kept == [str(entry)]
    assert report.created == []


def test_repair_recreates_a_deleted_menu_entry(workspace, linux, tmp_path):
    shortcuts.install_or_repair(workspace)
    entry = _applications(tmp_path / "home") / "com.suzent.app.desktop"
    entry.unlink()

    report = shortcuts.install_or_repair(workspace)

    assert entry.exists()
    assert report.created == [str(entry)]


def test_repair_rewrites_an_entry_pointing_at_the_wrong_target(
    workspace, linux, tmp_path
):
    shortcuts.install_or_repair(workspace)
    entry = _applications(tmp_path / "home") / "com.suzent.app.desktop"
    entry.write_text("[Desktop Entry]\nExec=/old/install/suzent-ui\n", encoding="utf-8")

    report = shortcuts.install_or_repair(workspace)

    assert report.repaired == [str(entry)]
    assert str(workspace / "bin" / "suzent-ui") in entry.read_text(encoding="utf-8")


def test_repair_does_not_resurrect_a_desktop_shortcut_the_user_deleted(
    workspace, linux, tmp_path
):
    shortcuts.install_or_repair(workspace, desktop=True)
    desktop_entry = tmp_path / "home" / "Desktop" / "com.suzent.app.desktop"
    assert desktop_entry.exists()
    desktop_entry.unlink()

    report = shortcuts.install_or_repair(workspace)

    assert not desktop_entry.exists()
    assert any("removed by the user" in note for note in report.notes)
    manifest = shortcuts.read_manifest(workspace)
    assert manifest["options"]["desktop"] is False

    # ...but asking for it again explicitly still brings it back.
    shortcuts.install_or_repair(workspace, desktop=True)
    assert desktop_entry.exists()


def test_disabling_the_desktop_shortcut_removes_it(workspace, linux, tmp_path):
    shortcuts.install_or_repair(workspace, desktop=True)
    desktop_entry = tmp_path / "home" / "Desktop" / "com.suzent.app.desktop"

    report = shortcuts.install_or_repair(workspace, desktop=False)

    assert not desktop_entry.exists()
    assert report.removed == [str(desktop_entry)]


def test_missing_ui_binary_is_reported_without_touching_shortcuts(workspace, linux):
    (workspace / "bin" / "suzent-ui").unlink()

    report = shortcuts.install_or_repair(workspace)

    assert not report.ok
    assert "desktop UI binary is missing" in report.notes[0]
    assert not shortcuts.manifest_path(workspace).exists()


def test_remove_deletes_only_recorded_entries(workspace, linux, tmp_path):
    shortcuts.install_or_repair(workspace)
    handmade = _applications(tmp_path / "home") / "my-own-suzent.desktop"
    handmade.write_text("[Desktop Entry]\n", encoding="utf-8")

    report = shortcuts.remove(workspace)

    assert report.removed == [
        str(_applications(tmp_path / "home") / "com.suzent.app.desktop")
    ]
    assert handmade.exists()
    assert not shortcuts.manifest_path(workspace).exists()


def test_linux_install_replaces_the_legacy_desktop_file(workspace, linux, tmp_path):
    applications = _applications(tmp_path / "home")
    applications.mkdir(parents=True)
    legacy = applications / "suzent.desktop"
    legacy.write_text(
        f'[Desktop Entry]\nExec="{workspace / "bin" / "suzent-ui"}"\n', encoding="utf-8"
    )

    shortcuts.install_or_repair(workspace)

    assert not legacy.exists()
    assert (applications / "com.suzent.app.desktop").exists()


def test_windows_entries_come_from_the_folders_powershell_reports(
    workspace, monkeypatch, tmp_path
):
    monkeypatch.setattr(shortcuts, "IS_WINDOWS", True)
    monkeypatch.setattr(shortcuts, "IS_MACOS", False)
    monkeypatch.setattr(shortcuts, "_DESKTOP_DEFAULT", True)
    (workspace / "bin" / "suzent-ui.exe").write_text("", encoding="utf-8")
    # Start Menu and Desktop are redirected here, as they are under OneDrive.
    redirected = tmp_path / "home" / "OneDrive"
    folders = {"application_menu": redirected / "Programs", "desktop": redirected}

    def fake_powershell(command):
        lines = []
        for kind, folder in folders.items():
            if f"kind = '{kind}'" not in command[-1]:
                continue
            folder.mkdir(parents=True, exist_ok=True)
            link = folder / "Suzent.lnk"
            state = "kept" if link.exists() else "created"
            link.write_text(str(workspace / "bin" / "suzent-ui.exe"), encoding="utf-8")
            lines.append(f"{state}\t{kind}\t{link}")
        return subprocess.CompletedProcess(command, 0, "\n".join(lines), "")

    monkeypatch.setattr(shortcuts, "_run", fake_powershell)
    report = shortcuts.install_or_repair(workspace)

    assert sorted(report.created) == sorted(
        str(folder / "Suzent.lnk") for folder in folders.values()
    )
    recorded = {
        item["kind"]: item["path"]
        for item in shortcuts.read_manifest(workspace)["entries"]
    }
    assert recorded["desktop"] == str(redirected / "Suzent.lnk")

    # A deleted desktop shortcut stays deleted, the Start Menu entry does not.
    (redirected / "Suzent.lnk").unlink()
    report = shortcuts.install_or_repair(workspace)

    assert not (redirected / "Suzent.lnk").exists()
    assert report.kept == [str(redirected / "Programs" / "Suzent.lnk")]


def test_macos_bundle_carries_the_installed_version_and_stable_target(
    workspace, macos, tmp_path
):
    report = shortcuts.install_or_repair(workspace)

    bundle = tmp_path / "home" / "Applications" / "Suzent.app"
    assert report.created == [str(bundle)]
    info = plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleShortVersionString"] == "1.2.3"
    assert info["CFBundleIdentifier"] == "com.suzent.app"
    launcher = (bundle / "Contents" / "MacOS" / "Suzent").read_text(encoding="utf-8")
    assert str(workspace / "bin" / "suzent-ui") in launcher
    assert shortcuts.install_or_repair(workspace).kept == [str(bundle)]


def test_macos_repair_replaces_the_legacy_symlinked_bundle(workspace, macos, tmp_path):
    legacy_bundle = workspace / "Suzent.app"
    (legacy_bundle / "Contents" / "MacOS").mkdir(parents=True)
    (legacy_bundle / "Contents" / "MacOS" / "Suzent").write_text(
        f'#!/bin/sh\nexec "{workspace / "bin" / "suzent-ui"}" "$@"\n', encoding="utf-8"
    )
    applications = tmp_path / "home" / "Applications"
    applications.mkdir(parents=True)
    (applications / "Suzent.app").symlink_to(legacy_bundle)

    report = shortcuts.install_or_repair(workspace)

    bundle = applications / "Suzent.app"
    assert not bundle.is_symlink()
    assert (bundle / "Contents" / "Info.plist").exists()
    assert not legacy_bundle.exists()
    assert report.repaired == [str(bundle)]


@pytest.mark.parametrize("operation", ["install", "remove"])
def test_macos_preserves_unowned_bundle(workspace, macos, tmp_path, operation):
    bundle = tmp_path / "home" / "Applications" / "Suzent.app"
    bundle.mkdir(parents=True)
    marker = bundle / "user-file"
    marker.write_text("keep me")
    if operation == "install":
        report = shortcuts.install_or_repair(workspace)
        assert not report.ok
    else:
        shortcuts.remove(workspace)
    assert marker.read_text() == "keep me"


def test_macos_preserves_replaced_recorded_bundle(workspace, macos, tmp_path):
    shortcuts.install_or_repair(workspace)
    bundle = tmp_path / "home" / "Applications" / "Suzent.app"
    launcher = bundle / "Contents" / "MacOS" / "Suzent"
    launcher.write_text("user replacement")
    assert not shortcuts.install_or_repair(workspace).ok
    assert not shortcuts.remove(workspace).ok
    assert launcher.read_text() == "user replacement"
    assert shortcuts.read_manifest(workspace)["entries"]


def test_macos_preserves_unowned_desktop_bundle(workspace, macos, tmp_path):
    alias = tmp_path / "home" / "Desktop" / "Suzent.app"
    alias.mkdir()
    marker = alias / "user-file"
    marker.touch()
    report = shortcuts.install_or_repair(workspace, desktop=True)
    assert not report.ok
    assert marker.exists()


@pytest.mark.parametrize("platform", ["linux", "macos"])
def test_failed_repair_retains_entry_for_uninstall(
    workspace, monkeypatch, tmp_path, platform, request
):
    request.getfixturevalue(platform)
    shortcuts.install_or_repair(workspace)
    original = shortcuts.read_manifest(workspace)["entries"]

    def fail_write(*args):
        args[-1].ok = False
        return False

    helper = (
        "_write_macos_bundle" if platform == "macos" else "_write_linux_desktop_file"
    )
    with monkeypatch.context() as patch:
        patch.setattr(shortcuts, helper, fail_write)
        assert not shortcuts.install_or_repair(workspace).ok
    assert shortcuts.read_manifest(workspace)["entries"] == original
    assert shortcuts.remove(workspace).ok
    assert not shortcuts.manifest_path(workspace).exists()
    assert not Path(original[0]["path"]).exists()


@pytest.mark.parametrize("disable", [False, True])
def test_failed_removal_can_be_retried(workspace, linux, monkeypatch, disable):
    shortcuts.install_or_repair(workspace, desktop=True)
    with monkeypatch.context() as patch:
        patch.setattr(shortcuts, "_remove_path", lambda path: False)
        report = (
            shortcuts.install_or_repair(workspace, desktop=False)
            if disable
            else shortcuts.remove(workspace)
        )
    assert not report.ok
    assert len(shortcuts.read_manifest(workspace)["entries"]) == 2
    assert shortcuts.remove(workspace).ok
    assert not shortcuts.manifest_path(workspace).exists()


def test_macos_desktop_alias_removed_with_bundle(workspace, macos, tmp_path):
    shortcuts.install_or_repair(workspace, desktop=True)
    assert shortcuts.install_or_repair(
        workspace, desktop=False, application_menu=False
    ).ok
    alias = tmp_path / "home" / "Desktop" / "Suzent.app"
    assert not alias.is_symlink()
    assert shortcuts.read_manifest(workspace)["entries"] == []


def test_macos_moved_workspace_repairs_recorded_target(workspace, macos, tmp_path):
    shortcuts.install_or_repair(workspace)
    moved = workspace.with_name("moved")
    workspace.rename(moved)
    report = shortcuts.install_or_repair(moved)
    assert report.ok
    assert report.repaired
    assert shortcuts.remove(moved).ok


def test_macos_failed_bundle_swap_restores_original(workspace, macos, monkeypatch):
    shortcuts.install_or_repair(workspace)
    original = shortcuts.read_manifest(workspace)["entries"]
    bundle = Path(original[0]["path"])
    plist = (bundle / "Contents" / "Info.plist").read_bytes()
    (workspace / ".suzent" / "release-tag").write_text("v1.2.4")
    rename = Path.rename

    def fail_replacement(path, target):
        if path.name == "replacement":
            raise OSError("simulated swap failure")
        return rename(path, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "rename", fail_replacement)
        assert not shortcuts.install_or_repair(workspace).ok
    assert (bundle / "Contents" / "Info.plist").read_bytes() == plist
    assert shortcuts.read_manifest(workspace)["entries"] == original
    assert shortcuts.install_or_repair(workspace).ok
