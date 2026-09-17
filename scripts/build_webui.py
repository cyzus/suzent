"""Build the frontend and stage it as backend package data.

`suzent web` serves the SPA out of `src/suzent/webui/`. That directory is a
build artifact, not source: it is gitignored and produced here, then picked up
by hatchling's `artifacts` list at wheel time.

Usage:
    python scripts/build_webui.py            # npm run build, then stage
    python scripts/build_webui.py --no-build # stage an existing frontend/dist
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist"
TARGET = ROOT / "src" / "suzent" / "webui"


def build_frontend() -> None:
    print("Building frontend (npm run build)...")
    subprocess.run(
        ["npm", "run", "build"],
        cwd=FRONTEND,
        check=True,
        # npm is a .cmd shim on Windows, which execve cannot run directly.
        shell=sys.platform == "win32",
    )


def stage() -> None:
    if not (DIST / "index.html").is_file():
        raise SystemExit(f"No build output at {DIST}. Run without --no-build.")
    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(DIST, TARGET)
    count = sum(1 for p in TARGET.rglob("*") if p.is_file())
    print(f"Staged {count} files into {TARGET.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Skip npm and stage whatever is already in frontend/dist",
    )
    args = parser.parse_args()
    if not args.no_build:
        build_frontend()
    stage()


if __name__ == "__main__":
    main()
