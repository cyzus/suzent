"""Linux systemd user-service implementation for Suzent."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from suzent.service.platforms.base import SERVICE_DESCRIPTION, PlatformServiceManager

UNIT_NAME = "suzent.service"


class LinuxServiceManager(PlatformServiceManager):
    @property
    def definition_path(self) -> Path:
        return Path.home() / ".config" / "systemd" / "user" / UNIT_NAME

    def _systemctl(
        self, *args: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["systemctl", "--user", *args],
            check=check,
            capture_output=True,
            text=True,
        )

    def is_installed(self) -> bool:
        return self.definition_path.exists()

    def is_autostart_enabled(self) -> bool:
        if not self.is_installed():
            return False
        return self._systemctl("is-enabled", UNIT_NAME, check=False).returncode == 0

    def install(self) -> None:
        self.definition_path.parent.mkdir(parents=True, exist_ok=True)
        command = " ".join(shlex.quote(arg) for arg in self.runtime_arguments)
        unit = (
            "[Unit]\n"
            f"Description={SERVICE_DESCRIPTION}\n"
            "After=network-online.target\n"
            "Wants=network-online.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"ExecStart={command}\n"
            "Restart=on-failure\n"
            "RestartSec=5\n"
            "TimeoutStopSec=15\n\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )
        self.definition_path.write_text(unit, encoding="utf-8")
        self._systemctl("daemon-reload")
        self._systemctl("enable", UNIT_NAME)

    def uninstall(self) -> None:
        if self.is_installed():
            self._systemctl("disable", "--now", UNIT_NAME, check=False)
            self.definition_path.unlink(missing_ok=True)
            self._systemctl("daemon-reload")

    def start(self) -> None:
        self._systemctl("start", UNIT_NAME)

    def stop(self) -> None:
        self._systemctl("stop", UNIT_NAME, check=False)
