"""macOS LaunchAgent implementation for the Suzent user service."""

from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path

from suzent.service.platforms.base import PlatformServiceManager

LABEL = "com.suzent.service"


class MacOSServiceManager(PlatformServiceManager):
    @property
    def definition_path(self) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"

    @property
    def domain(self) -> str:
        return f"gui/{os.getuid()}"

    def is_installed(self) -> bool:
        return self.definition_path.exists()

    def install(self) -> None:
        self.definition_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "Label": LABEL,
            "ProgramArguments": self.runtime_arguments,
            "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},
            "ProcessType": "Background",
            "StandardOutPath": str(self.log_path),
            "StandardErrorPath": str(self.log_path),
        }
        with self.definition_path.open("wb") as handle:
            plistlib.dump(payload, handle)

    def uninstall(self) -> None:
        self.stop()
        self.definition_path.unlink(missing_ok=True)

    def start(self) -> None:
        loaded = (
            subprocess.run(
                ["launchctl", "print", f"{self.domain}/{LABEL}"],
                check=False,
                capture_output=True,
            ).returncode
            == 0
        )
        if loaded:
            subprocess.run(
                ["launchctl", "kickstart", f"{self.domain}/{LABEL}"], check=True
            )
            return
        subprocess.run(
            ["launchctl", "bootstrap", self.domain, str(self.definition_path)],
            check=True,
        )

    def stop(self) -> None:
        subprocess.run(
            ["launchctl", "bootout", self.domain, str(self.definition_path)],
            check=False,
            capture_output=True,
        )
