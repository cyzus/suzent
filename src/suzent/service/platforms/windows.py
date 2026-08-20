"""Administrator-free Windows user-service implementation for Suzent."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import psutil

from suzent.config import RUNTIME_DIR
from suzent.service.platforms.base import PlatformServiceManager
from suzent.service.state import read_process_state

try:
    import winreg
except ImportError:  # pragma: no cover - imported by cross-platform unit tests
    winreg = None

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "Suzent Service"
SUPERVISOR_PATH = RUNTIME_DIR / "service-supervisor.pyw"
STOP_REQUEST_PATH = RUNTIME_DIR / "service-stop.request"

# Legacy paths from the cmd.exe-based supervisor; cleaned up on install/uninstall.
_LEGACY_CMD = RUNTIME_DIR / "service-supervisor.cmd"
_LEGACY_LAUNCHER = RUNTIME_DIR / "service-launcher.pyw"


class WindowsServiceManager(PlatformServiceManager):
    @property
    def definition_path(self) -> Path:
        return SUPERVISOR_PATH

    def _read_autostart(self) -> str | None:
        if winreg is None:
            return None
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, _kind = winreg.QueryValueEx(key, RUN_VALUE)
        except OSError:
            return None
        return str(value)

    def _set_autostart(self, command: str) -> None:
        if winreg is None:
            raise RuntimeError("Windows registry support is unavailable.")
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, RUN_KEY, access=winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, command)

    def _delete_autostart(self) -> None:
        if winreg is None:
            return
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, RUN_KEY, access=winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, RUN_VALUE)
        except OSError:
            pass

    def is_installed(self) -> bool:
        return self.definition_path.exists() and self._read_autostart() is not None

    def _pythonw(self) -> Path:
        pythonw = self.python_executable.with_name("pythonw.exe")
        if os.name == "nt" and not pythonw.is_file():
            raise RuntimeError(f"Windowless Python launcher not found at {pythonw}")
        return pythonw

    def _autostart_command(self) -> str:
        return subprocess.list2cmdline(
            [str(self._pythonw()), str(self.definition_path)]
        )

    def _ensure_autostart(self) -> None:
        """Migrate stale autostart entries (including the old launcher path)."""
        command = self._autostart_command()
        if self._read_autostart() != command:
            self._set_autostart(command)

    @staticmethod
    def _cleanup_legacy() -> None:
        _LEGACY_CMD.unlink(missing_ok=True)
        _LEGACY_LAUNCHER.unlink(missing_ok=True)

    def install(self) -> None:
        self.definition_path.parent.mkdir(parents=True, exist_ok=True)
        python = str(self.python_executable)
        stop_request = str(STOP_REQUEST_PATH)
        # The supervisor is a .pyw script run by pythonw.exe — a GUI-subsystem
        # binary that never allocates a console window.  The old approach used
        # cmd.exe to run a .cmd batch, which could flash a terminal on Win 11
        # (Windows Terminal intercepts console-subsystem process creation) and
        # combined the MSDN-incompatible CREATE_NO_WINDOW | DETACHED_PROCESS
        # flags.
        script = (
            "import subprocess, sys, time\n"
            "from pathlib import Path\n\n"
            f"STOP_REQUEST = Path({stop_request!r})\n"
            f"PYTHON = {python!r}\n"
            "MAX_RETRIES = 3\n"
            "CREATE_NO_WINDOW = 0x08000000\n\n"
            "if STOP_REQUEST.exists():\n"
            "    STOP_REQUEST.unlink(missing_ok=True)\n\n"
            "retries = 0\n"
            "while True:\n"
            "    if STOP_REQUEST.exists():\n"
            "        STOP_REQUEST.unlink(missing_ok=True)\n"
            "        break\n"
            "    code = subprocess.call(\n"
            '        [PYTHON, "-m", "suzent.service.runtime"],\n'
            "        stdin=subprocess.DEVNULL,\n"
            "        stdout=subprocess.DEVNULL,\n"
            "        stderr=subprocess.DEVNULL,\n"
            "        creationflags=CREATE_NO_WINDOW,\n"
            "    )\n"
            "    if STOP_REQUEST.exists():\n"
            "        STOP_REQUEST.unlink(missing_ok=True)\n"
            "        break\n"
            "    if code == 0 or code == 73:\n"
            "        break\n"
            "    retries += 1\n"
            "    if retries >= MAX_RETRIES:\n"
            "        break\n"
            "    time.sleep(5)\n"
        )
        self.definition_path.write_text(script, encoding="utf-8")
        self._set_autostart(self._autostart_command())
        self._cleanup_legacy()

    def uninstall(self) -> None:
        self._delete_autostart()
        self.stop()
        self.definition_path.unlink(missing_ok=True)
        STOP_REQUEST_PATH.unlink(missing_ok=True)
        self._cleanup_legacy()

    def start(self) -> None:
        self._ensure_autostart()
        if read_process_state() is not None:
            return
        STOP_REQUEST_PATH.unlink(missing_ok=True)
        # pythonw.exe is a GUI-subsystem binary — it never creates a console
        # window, even without creation flags.  CREATE_NEW_PROCESS_GROUP lets
        # the supervisor outlive the parent (CLI / Tauri).
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(
            [str(self._pythonw()), str(self.definition_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creationflags,
        )

    def stop(self) -> None:
        STOP_REQUEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        STOP_REQUEST_PATH.touch()
        state = read_process_state()
        if state is None:
            return
        try:
            process = psutil.Process(state.pid)
            process.terminate()
            process.wait(timeout=5)
        except psutil.TimeoutExpired:
            process.kill()
        except psutil.Error:
            pass
        time.sleep(0.1)
