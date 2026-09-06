"""Register a per-user, discovery-only native messaging host after pairing."""

import json
import os
import shlex
import sys
from pathlib import Path

from suzent.config.paths import DATA_DIR, USER_CONFIG_DIR

HOST_NAME = "com.suzent.browser"


def install_native_host(origin: str) -> None:
    directory = USER_CONFIG_DIR / "browser-extension-host"
    directory.mkdir(parents=True, exist_ok=True)
    helper = Path(__file__).with_name("native_host.py")
    port_file = DATA_DIR / "runtime" / "server.port"
    if sys.platform == "win32":
        import winreg

        launcher = directory / "launch.cmd"
        # cmd expands percent-delimited environment names even inside quotes.
        values = [str(value) for value in (sys.executable, helper, port_file)]
        if any(any(char in value for char in '%\r\n"') for value in values):
            raise OSError("Native messaging paths contain unsupported characters")
        launcher.write_text(
            "@echo off\n" + " ".join(f'"{value}"' for value in values) + "\n",
            encoding="utf-8",
        )
        locations = [directory / "host.json"]
    else:
        launcher = directory / "launch.sh"
        launcher.write_text(
            "#!/bin/sh\nexec "
            + shlex.join([sys.executable, str(helper), str(port_file)])
            + "\n",
            encoding="utf-8",
        )
        launcher.chmod(0o700)
        if sys.platform == "darwin":
            root = Path.home() / "Library/Application Support"
            locations = [
                root / browser / "NativeMessagingHosts" / f"{HOST_NAME}.json"
                for browser in ("Google/Chrome", "Microsoft Edge")
            ]
        else:
            root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
            locations = [
                root / browser / "NativeMessagingHosts" / f"{HOST_NAME}.json"
                for browser in ("google-chrome", "chromium", "microsoft-edge")
            ]
    manifest = json.dumps(
        {
            "name": HOST_NAME,
            "description": "Locate the local Suzent backend",
            "path": str(launcher),
            "type": "stdio",
            "allowed_origins": [origin + "/"],
        },
        indent=2,
    )
    for location in locations:
        location.parent.mkdir(parents=True, exist_ok=True)
        location.write_text(manifest, encoding="utf-8")
    if sys.platform == "win32":
        for browser in ("Google\\Chrome", "Microsoft\\Edge"):
            with winreg.CreateKey(
                winreg.HKEY_CURRENT_USER,
                f"Software\\{browser}\\NativeMessagingHosts\\{HOST_NAME}",
            ) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(locations[0]))
