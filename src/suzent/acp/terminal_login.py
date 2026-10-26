"""Launch operator-requested login in a real, visible terminal on the host."""

import asyncio
import contextlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

import psutil

from suzent.acp.pairing import private_write
from suzent.acp.terminal_worker import stop_tree


def terminal_command(worker: list[str]) -> list[str] | None:
    if sys.platform == "win32":
        return worker
    if sys.platform == "darwin":
        script = 'on run argv\ntell application "Terminal"\nactivate\ndo script (item 1 of argv)\nend tell\nend run'
        return ["osascript", "-e", script, shlex.join(worker)]
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return None
    for name, args in [
        ("x-terminal-emulator", ["-e"]),
        ("gnome-terminal", ["--wait", "--"]),
        ("konsole", ["--nofork", "-e"]),
        ("xterm", ["-e"]),
    ]:
        if executable := shutil.which(name):
            return [executable, *args, *worker]
    return None


def terminal_available() -> bool:
    return terminal_command([sys.executable]) is not None


async def run_terminal_login(
    command: list[str], cwd: str, env: dict[str, str], *, timeout: float = 300
) -> None:
    if not command or not (
        executable := shutil.which(
            command[0], path=env.get("PATH", os.environ.get("PATH"))
        )
    ):
        raise ValueError("Login executable is not installed")
    with tempfile.TemporaryDirectory(prefix="suzent-acp-login-") as root:
        directory = Path(root)
        directory.chmod(0o700)
        worker = [
            sys.executable,
            str(Path(__file__).with_name("terminal_worker.py")),
            root,
        ]
        invocation = terminal_command(worker)
        if invocation is None:
            raise ValueError("No interactive terminal is available on this host")
        private_write(
            directory / "config.json",
            {
                "command": [executable, *command[1:]],
                "cwd": cwd,
                "env": env,
                "parent_pid": os.getpid(),
                "parent_created": psutil.Process().create_time(),
            },
        )
        flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        launcher = subprocess.Popen(
            invocation,
            creationflags=flags,
            **(
                {}
                if flags
                else {
                    "stdin": subprocess.DEVNULL,
                    "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL,
                }
            ),
        )
        state: dict = {}
        try:
            async with asyncio.timeout(timeout):
                started = asyncio.get_running_loop().time()
                while True:
                    path = directory / "state.json"
                    if path.exists():
                        state = json.loads(path.read_text(encoding="utf-8"))
                    if "exit_code" in state:
                        if state["exit_code"] != 0:
                            raise ValueError("Login was closed or failed; try again")
                        return
                    if not state and (
                        launcher.poll() not in (None, 0)
                        or asyncio.get_running_loop().time() - started > 15
                    ):
                        raise ValueError("Could not open the login terminal")
                    if state:
                        try:
                            alive = (
                                psutil.Process(state["pid"]).create_time()
                                == state["created"]
                            )
                        except psutil.NoSuchProcess:
                            alive = False
                        if not alive:
                            # The worker may have written the final state since this read.
                            final = json.loads(path.read_text(encoding="utf-8"))
                            if final.get("exit_code") == 0:
                                return
                            raise ValueError("Login terminal was closed")
                    await asyncio.sleep(0.2)
        finally:
            (directory / "cancel").touch()
            path = directory / "state.json"
            if path.exists():
                state = json.loads(path.read_text(encoding="utf-8"))
            if "pid" in state:
                with contextlib.suppress(psutil.Error):
                    process = psutil.Process(state["pid"])
                    if process.create_time() == state["created"]:
                        stop_tree(process)
            if launcher.poll() is None:
                with contextlib.suppress(psutil.Error):
                    stop_tree(psutil.Process(launcher.pid))
            with contextlib.suppress(subprocess.TimeoutExpired):
                await asyncio.to_thread(launcher.wait, timeout=3)
