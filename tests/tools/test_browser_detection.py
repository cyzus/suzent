from pathlib import Path

import pytest

from suzent.tools.browser import detection as browser_detection


def windows_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(browser_detection.sys, "platform", "win32")
    for name in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "HOMEDRIVE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user"))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "system"))
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path / "system-x86"))


@pytest.mark.parametrize("root", ["user", "system", "system-x86"])
def test_windows_installs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, root: str
) -> None:
    windows_environment(monkeypatch, tmp_path)
    chrome = tmp_path / root / "Google/Chrome/Application/chrome.exe"
    edge = tmp_path / root / "Microsoft/Edge/Application/msedge.exe"
    for executable in (chrome, edge):
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.touch()
    assert browser_detection.available_browsers() == {
        "chromium": True,
        "chrome": True,
        "msedge": True,
    }
    edge.unlink()
    assert not browser_detection.available_browsers()["msedge"]


def test_no_installs_keeps_chromium(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    windows_environment(monkeypatch, tmp_path)
    assert browser_detection.available_browsers() == {
        "chromium": True,
        "chrome": False,
        "msedge": False,
    }


@pytest.mark.parametrize(
    "platform,installed",
    [
        ("darwin", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ("linux", "/opt/google/chrome/chrome"),
    ],
)
def test_other_platform_paths(
    monkeypatch: pytest.MonkeyPatch, platform: str, installed: str
) -> None:
    monkeypatch.setattr(browser_detection.sys, "platform", platform)
    monkeypatch.setattr(Path, "is_file", lambda path: path == Path(installed))
    assert browser_detection.available_browsers() == {
        "chromium": True,
        "chrome": True,
        "msedge": False,
    }


def test_unreadable_install_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    windows_environment(monkeypatch, tmp_path)

    def denied(path: Path) -> bool:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "is_file", denied)
    assert browser_detection.available_browsers() == {
        "chromium": True,
        "chrome": False,
        "msedge": False,
    }
