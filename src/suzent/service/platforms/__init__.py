"""Platform service-manager adapters."""

from __future__ import annotations

import sys

from suzent.service.platforms.base import PlatformServiceManager


def get_platform_manager() -> PlatformServiceManager:
    if sys.platform == "win32":
        from suzent.service.platforms.windows import WindowsServiceManager

        return WindowsServiceManager()
    if sys.platform == "darwin":
        from suzent.service.platforms.macos import MacOSServiceManager

        return MacOSServiceManager()

    from suzent.service.platforms.linux import LinuxServiceManager

    return LinuxServiceManager()


__all__ = ["PlatformServiceManager", "get_platform_manager"]
