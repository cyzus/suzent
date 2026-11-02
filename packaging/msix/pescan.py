"""Fail if the MSIX runtime contains PE files signtool or the Store will reject.

Usage: python packaging/msix/pescan.py <runtime dir>

Checks every .exe/.dll/.pyd:
- it is a well-formed PE (MZ header, PE signature);
- it targets x64 (warning only: ARM64/x86 launcher stubs such as pip's or
  setuptools' are dead weight, but the PoC signed packages containing them);
- it is not one of the files the PoC bisected as making `signtool sign` fail
  with 0x800700C1 (Tcl/Tk and the app-local vcruntime).
"""

from __future__ import annotations

import os
import struct
import sys
from collections import Counter

KNOWN_BAD = {"tcl86t.dll", "tk86t.dll", "vcruntime140.dll", "vcruntime140_1.dll"}
MACHINE_X64 = 0x8664


def scan(root: str) -> list[str]:
    problems: list[str] = []
    machines: Counter[str] = Counter()
    for directory, _, files in os.walk(root):
        for name in files:
            if not name.lower().endswith((".exe", ".dll", ".pyd")):
                continue
            path = os.path.join(directory, name)
            rel = os.path.relpath(path, root)
            if name.lower() in KNOWN_BAD:
                problems.append(f"KNOWN-BAD {rel}")
                continue
            with open(path, "rb") as handle:
                head = handle.read(4096)
            if head[:2] != b"MZ":
                problems.append(f"NOT-MZ {rel}")
                continue
            offset = struct.unpack_from("<I", head, 0x3C)[0]
            if offset + 6 > len(head) or head[offset : offset + 4] != b"PE\0\0":
                problems.append(f"BAD-PE {rel}")
                continue
            machine = struct.unpack_from("<H", head, offset + 4)[0]
            machines[hex(machine)] += 1
            if machine != MACHINE_X64:
                # Reported, not fatal: the PoC signed packages containing these.
                print(f"warning: NOT-X64 {hex(machine)} {rel}")
    print(f"PE files by machine type: {dict(machines)}")
    return problems


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    problems = scan(sys.argv[1])
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} PE problem(s) found")
        return 1
    print("PE scan ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
