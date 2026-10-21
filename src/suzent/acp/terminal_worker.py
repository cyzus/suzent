"""Run a login in a native terminal; keep terminal output out of the API/logs."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil


def write_state(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    os.replace(temporary, path)


def stop_tree(process: psutil.Process) -> None:
    try:
        children = process.children(recursive=True)
    except psutil.NoSuchProcess:
        return
    for item in [*reversed(children), process]:
        try:
            item.kill()
        except psutil.NoSuchProcess:
            pass


def main(directory: Path) -> int:
    config_path = directory / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config_path.unlink()
    state_path = directory / "state.json"
    identity = {"pid": os.getpid(), "created": psutil.Process().create_time()}
    write_state(state_path, identity)
    child: subprocess.Popen | None = None
    code = 1
    try:
        if (directory / "cancel").exists():
            return 1
        child = subprocess.Popen(
            config["command"], cwd=config["cwd"], env=config["env"]
        )
        deadline = time.monotonic() + 300
        while child.poll() is None:
            parent_alive = False
            try:
                parent_alive = (
                    psutil.Process(config["parent_pid"]).create_time()
                    == config["parent_created"]
                )
            except psutil.NoSuchProcess:
                pass
            if (
                (directory / "cancel").exists()
                or not parent_alive
                or time.monotonic() >= deadline
            ):
                stop_tree(psutil.Process(child.pid))
                break
            time.sleep(0.2)
        code = child.wait()
    except (OSError, psutil.Error):
        code = 1
    finally:
        if child is not None and child.poll() is None:
            stop_tree(psutil.Process(child.pid))
        if directory.exists():
            write_state(state_path, {**identity, "exit_code": code})
    return code


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
