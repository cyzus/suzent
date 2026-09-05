"""Detect stable browser channels at the locations Playwright launches from."""

import os
import sys
from pathlib import Path


def available_browsers() -> dict[str, bool]:
    # Chromium can be provisioned by the managed browser's existing installer.
    available = {"chromium": True, "chrome": False, "msedge": False}
    match sys.platform:
        case "win32":
            roots = [
                os.environ.get(name)
                for name in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)")
            ]
            drive = os.environ.get("HOMEDRIVE")
            if drive:
                roots.extend(
                    [drive + "\\Program Files", drive + "\\Program Files (x86)"]
                )
            candidates = {
                "chrome": [
                    Path(root) / "Google/Chrome/Application/chrome.exe"
                    for root in roots
                    if root
                ],
                "msedge": [
                    Path(root) / "Microsoft/Edge/Application/msedge.exe"
                    for root in roots
                    if root
                ],
            }
        case "darwin":
            candidates = {
                "chrome": [
                    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
                ],
                "msedge": [
                    Path(
                        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
                    )
                ],
            }
        case "linux":
            candidates = {
                "chrome": [Path("/opt/google/chrome/chrome")],
                "msedge": [Path("/opt/microsoft/msedge/msedge")],
            }
        case _:
            return available
    for channel, paths in candidates.items():
        for path in paths:
            try:
                if path.is_file():
                    available[channel] = True
                    break
            except OSError:
                continue
    return available
