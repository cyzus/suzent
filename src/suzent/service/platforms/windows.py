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
SUPERVISOR_PATH = RUNTIME_DIR / "service-supervisor.cmd"
LAUNCHER_PATH = RUNTIME_DIR / "service-launcher.pyw"
STOP_REQUEST_PATH = RUNTIME_DIR / "service-stop.request"


class WindowsServiceManager(PlatformServiceManager):
    @property
    def definition_path(self) -> Path:
        return SUPERVISOR_PATH

    @property
    def launcher_path(self) -> Path:
        return LAUNCHER_PATH

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

    def _autostart_command(self) -> str:
        pythonw = self.python_executable.with_name("pythonw.exe")
        if os.name == "nt" and not pythonw.is_file():
            raise RuntimeError(f"Windowless Python launcher not found at {pythonw}")
        return subprocess.list2cmdline([str(pythonw), str(self.launcher_path)])

    def _write_hidden_launcher(self) -> None:
        script = (
            "import subprocess\n\n"
            "creationflags = (\n"
            '    getattr(subprocess, "CREATE_NO_WINDOW", 0)\n'
            '    | getattr(subprocess, "DETACHED_PROCESS", 0)\n'
            '    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)\n'
            ")\n"
            "subprocess.Popen(\n"
            f'    ["cmd.exe", "/d", "/c", {str(self.definition_path)!r}],\n'
            "    stdin=subprocess.DEVNULL,\n"
            "    stdout=subprocess.DEVNULL,\n"
            "    stderr=subprocess.DEVNULL,\n"
            "    close_fds=True,\n"
            "    creationflags=creationflags,\n"
            ")\n"
        )
        self.launcher_path.write_text(script, encoding="utf-8")

    def _ensure_hidden_autostart(self) -> None:
        command = self._autostart_command()
        self._write_hidden_launcher()
        if self._read_autostart() != command:
            self._set_autostart(command)

    def install(self) -> None:
        self.definition_path.parent.mkdir(parents=True, exist_ok=True)
        python = subprocess.list2cmdline([str(self.python_executable)])
        stop_request = str(STOP_REQUEST_PATH)
        script = (
            "@echo off\n"
            "setlocal\n"
            "set retries=0\n"
            f'if exist "{stop_request}" del /q "{stop_request}"\n'
            ":run\n"
            f'if exist "{stop_request}" (\n'
            f'  del /q "{stop_request}"\n'
            "  exit /b 0\n"
            ")\n"
            f"{python} -m suzent.service.runtime\n"
            "set code=%errorlevel%\n"
            f'if exist "{stop_request}" (\n'
            f'  del /q "{stop_request}"\n'
            "  exit /b 0\n"
            ")\n"
            "if %code% EQU 0 exit /b 0\n"
            "if %code% EQU 73 exit /b 73\n"
            "set /a retries+=1\n"
            "if %retries% GEQ 3 exit /b %code%\n"
            "timeout /t 5 /nobreak >nul\n"
            "goto run\n"
        )
        self.definition_path.write_text(script, encoding="utf-8")
        self._write_hidden_launcher()
        self._set_autostart(self._autostart_command())

    def uninstall(self) -> None:
        self._delete_autostart()
        self.stop()
        self.definition_path.unlink(missing_ok=True)
        self.launcher_path.unlink(missing_ok=True)
        STOP_REQUEST_PATH.unlink(missing_ok=True)

    def start(self) -> None:
        self._ensure_hidden_autostart()
        if read_process_state() is not None:
            return
        STOP_REQUEST_PATH.unlink(missing_ok=True)
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
        subprocess.Popen(
            ["cmd.exe", "/d", "/c", str(self.definition_path)],
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
