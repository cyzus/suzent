"""Windows helper that waits for the locked Suzent launcher before updating."""

import argparse
import ctypes
import os
import subprocess
import sys
from pathlib import Path


def _wait_for_process_exit(pid: int) -> None:
    """Wait for a Windows process, returning immediately if it already exited."""
    synchronize = 0x00100000
    infinite = 0xFFFFFFFF
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return
    try:
        kernel32.WaitForSingleObject(handle, infinite)
    finally:
        kernel32.CloseHandle(handle)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-pid", type=int, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args()

    _wait_for_process_exit(args.wait_pid)

    command = [sys.executable, "-m", "suzent.cli", "update"]
    if args.dev:
        command.append("--dev")
    result = subprocess.run(command, cwd=args.root, env=os.environ.copy())
    if result.returncode != 0 and sys.stdin.isatty():
        input("\nSuzent update failed. Press Enter to close.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
