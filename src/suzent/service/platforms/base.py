"""Common interface for user-level operating-system services."""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from pathlib import Path

from suzent.config import RUNTIME_DIR

SERVICE_DESCRIPTION = "Suzent Background Service"


class PlatformServiceManager(ABC):
    """Manage the current user's Suzent service definition."""

    @property
    def python_executable(self) -> Path:
        return Path(sys.executable).resolve()

    @property
    def log_path(self) -> Path:
        return RUNTIME_DIR / "server.log"

    @property
    def runtime_arguments(self) -> list[str]:
        return [str(self.python_executable), "-m", "suzent.service.runtime"]

    @abstractmethod
    def is_installed(self) -> bool: ...

    def is_autostart_enabled(self) -> bool:
        return self.is_installed()

    @abstractmethod
    def install(self) -> None: ...

    @abstractmethod
    def uninstall(self) -> None: ...

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    def restart(self) -> None:
        self.stop()
        self.start()
