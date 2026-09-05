"""Discover local browser debugging endpoints without opening profile databases."""

import os
import re
import sys
from pathlib import Path


def browser_user_data_dir(channel: str) -> Path:
    if channel not in {"chrome", "msedge"}:
        raise ValueError("Select Chrome or Edge to connect to an existing browser.")
    edge = channel == "msedge"
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return root / ("Microsoft/Edge" if edge else "Google/Chrome") / "User Data"
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library/Application Support"
            / ("Microsoft Edge" if edge else "Google/Chrome")
        )
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / (
        "microsoft-edge" if edge else "google-chrome"
    )


def discover_browser_endpoint(channel: str) -> str:
    try:
        lines = (
            (browser_user_data_dir(channel) / "DevToolsActivePort")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        if len(lines) != 2 or not lines[0].isdigit():
            raise ValueError
        port = int(lines[0])
        if not 1 <= port <= 65535 or not re.fullmatch(
            r"/devtools/browser/[a-zA-Z0-9-]+", lines[1]
        ):
            raise ValueError
    except (OSError, ValueError):
        raise ValueError(
            "Start the selected browser and enable remote debugging in its inspect page. "
            "Suzent could not find a valid local debugging endpoint."
        ) from None
    return f"ws://127.0.0.1:{port}{lines[1]}"
