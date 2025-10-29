#!/usr/bin/env python3
"""
Cross-platform dev starter.

Behavior
- If a virtual environment exists at `.venv`, this script will prefer the venv's Python executable.
- Starts the backend (`python src/suzent/server.py`) and the frontend (`npm run dev`) as child processes
  and forwards their stdout/stderr to the current terminal with a simple prefix.

Usage
  python start-dev.py         # runs both processes
  python start-dev.py --dry-run  # prints the commands that would be run
  python start-dev.py --venv-path myenv        # override venv location
  python start-dev.py --no-venv                # don't try to use a venv

"""
import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path


def find_venv_python(root: Path, venv_path: str) -> str | None:
    venv = root / venv_path
    if not venv.exists():
        return None
    # Windows
    win_python = venv / "Scripts" / "python.exe"
    # Unix
    nix_python = venv / "bin" / "python"
    if win_python.exists():
        return str(win_python)
    if nix_python.exists():
        return str(nix_python)
    return None


def stream_reader(prefix: str, stream, lock: threading.Lock):
    for line in iter(stream.readline, b""):
        try:
            text = line.decode(errors="replace").rstrip()
        except Exception:
            text = str(line)
        with lock:
            print(f"[{prefix}] {text}")
    stream.close()


def start_process(cmd, cwd=None, prefix=None, env=None):
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    lock = threading.Lock()
    t = threading.Thread(target=stream_reader, args=(prefix, proc.stdout, lock), daemon=True)
    t.start()
    return proc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--venv-path", default=".venv", help="Relative path to virtualenv folder (default: .venv)")
    parser.add_argument("--no-venv", action="store_true", help="Don't try to use a virtual environment")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    python_exec = None
    if not args.no_venv:
        python_exec = find_venv_python(root, args.venv_path)
    if not python_exec:
        python_exec = shutil.which("python") or sys.executable

    backend_cmd = [python_exec, str(root / "src" / "suzent" / "server.py")]
    frontend_cmd = [shutil.which("npm") or "npm", "run", "dev"]

    if args.dry_run:
        print("DRY RUN — commands that would be executed:")
        print("backend:", backend_cmd)
        print("frontend:", frontend_cmd, "(cwd=frontend)")
        return

    print("Starting backend and frontend. Press Ctrl-C to stop both.")

    procs = []
    try:
        # Start backend
        procs.append(start_process(backend_cmd, cwd=root, prefix="backend"))

        # Start frontend
        procs.append(start_process(frontend_cmd, cwd=root / "frontend", prefix="frontend"))

        # Wait until both processes exit or user interrupts.
        # Use poll + sleep instead of per-process wait(timeout=...) to avoid
        # subprocess.TimeoutExpired when a process is still running.
        while True:
            alive = [p for p in procs if p.poll() is None]
            if not alive:
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Received interrupt — terminating child processes...")
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
    finally:
        for p in procs:
            if p.poll() is None:
                try:
                    p.kill()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
