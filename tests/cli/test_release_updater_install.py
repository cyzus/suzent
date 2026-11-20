"""Installing the standalone updater while an older one is still open."""

import importlib
from pathlib import Path

import pytest

cli_main = importlib.import_module("suzent.cli.main")


@pytest.fixture
def windows_updater(monkeypatch, tmp_path: Path) -> Path:
    updater = tmp_path / "updater" / "suzent-installer.exe"
    updater.parent.mkdir()
    updater.write_bytes(b"old")
    (updater.parent / "version.txt").write_text("v0.27.1", encoding="utf-8")

    monkeypatch.setattr(cli_main, "IS_WINDOWS", True)
    monkeypatch.setattr(cli_main, "_persistent_updater_path", lambda: updater)
    monkeypatch.setattr(
        cli_main,
        "_download_release_asset",
        lambda asset, tag, dest: dest.write_bytes(b"new"),
    )
    monkeypatch.setattr(cli_main, "_verify_release_asset", lambda *args: None)
    monkeypatch.setattr(cli_main.time, "sleep", lambda seconds: None)
    return updater


def _lock(monkeypatch, *, overwrite: set[Path], rename: set[Path] = frozenset()):
    """Make Windows-style locks: no overwriting `overwrite`, no moving `rename`."""
    real_replace = Path.replace

    def replace(self: Path, target):
        target = Path(target)
        if target in overwrite and target.exists():
            raise PermissionError(5, "Access is denied", str(self))
        if self in rename:
            raise PermissionError(5, "Access is denied", str(self))
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", replace)


def test_open_updater_is_moved_aside_and_replaced(monkeypatch, windows_updater):
    _lock(monkeypatch, overwrite={windows_updater})

    assert cli_main._install_release_updater("v0.27.2") == windows_updater
    assert windows_updater.read_bytes() == b"new"
    assert (windows_updater.parent / "version.txt").read_text() == "v0.27.2"
    assert sorted(p.name for p in windows_updater.parent.iterdir()) == [
        "suzent-installer.exe",
        "version.txt",
    ]


def test_updater_that_cannot_be_moved_runs_from_a_versioned_file(
    monkeypatch, windows_updater
):
    _lock(monkeypatch, overwrite={windows_updater}, rename={windows_updater})

    updater = cli_main._install_release_updater("v0.27.2")

    assert updater.name.startswith("suzent-installer-v0.27.2-")
    assert updater.suffix == ".exe"
    assert updater.read_bytes() == b"new"
    assert windows_updater.read_bytes() == b"old"
    assert (windows_updater.parent / "version.txt").read_text() == "v0.27.1"
    assert not list(windows_updater.parent.glob("*.new"))


def test_stale_updaters_are_removed_after_a_clean_install(windows_updater):
    parent = windows_updater.parent
    (parent / ".suzent-installer.exe.123.old").write_bytes(b"x")
    (parent / "suzent-installer-v0.27.1.exe").write_bytes(b"x")

    assert cli_main._install_release_updater("v0.27.2") == windows_updater

    assert sorted(p.name for p in parent.iterdir()) == [
        "suzent-installer.exe",
        "version.txt",
    ]


def test_permission_error_outside_windows_is_not_hidden(monkeypatch, windows_updater):
    monkeypatch.setattr(cli_main, "IS_WINDOWS", False)
    _lock(monkeypatch, overwrite={windows_updater})

    with pytest.raises(PermissionError):
        cli_main._install_release_updater("v0.27.2")
    assert windows_updater.read_bytes() == b"old"


def test_prefetch_does_not_use_a_fallback_the_desktop_cannot_apply(
    monkeypatch, windows_updater
):
    _lock(monkeypatch, overwrite={windows_updater}, rename={windows_updater})

    with pytest.raises(PermissionError):
        cli_main._install_release_updater("v0.27.2", allow_fallback=False)
    assert sorted(p.name for p in windows_updater.parent.iterdir()) == [
        "suzent-installer.exe",
        "version.txt",
    ]
