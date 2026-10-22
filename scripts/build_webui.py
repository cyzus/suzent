"""Build the frontend and stage it as backend package data.

`suzent web` serves the SPA out of `src/suzent/webui/`. That directory is a
build artifact, not source: it is gitignored and produced here, then picked up
by hatchling's `artifacts` list at wheel time.

Release CI also packs the bundle as the `suzent-webui.zip` release asset, so
an install without Node (a headless Linux server, say) can still serve
`suzent web`: setup.sh and setup.ps1 download it and unpack it here.

Usage:
    python scripts/build_webui.py            # npm run build, then stage
    python scripts/build_webui.py --no-build # stage an existing frontend/dist
    python scripts/build_webui.py --archive suzent-webui.zip   # build, stage, pack
    python scripts/build_webui.py --install-archive suzent-webui.zip
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
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


def pack(archive: Path) -> None:
    """Zip the staged bundle with index.html at the archive root."""
    archive.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in TARGET.rglob("*") if p.is_file())
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            bundle.write(path, path.relative_to(TARGET).as_posix())
    print(f"Packed {len(files)} files into {archive}")


def install_archive(archive: Path) -> None:
    """Replace the staged bundle with the contents of a release archive.

    Unpacks beside the target and swaps it in only once the whole archive is
    out, so a bad download leaves the previous bundle serving.
    """
    staging = TARGET.with_name(TARGET.name + ".staging")
    previous = TARGET.with_name(TARGET.name + ".previous")
    for leftover in (staging, previous):
        if leftover.exists():
            shutil.rmtree(leftover)
    with zipfile.ZipFile(archive) as bundle:
        root = staging.resolve()
        for name in bundle.namelist():
            dest = (staging / name).resolve()
            if dest != root and root not in dest.parents:
                raise SystemExit(f"Refusing archive entry outside the bundle: {name}")
        bundle.extractall(staging)
    if not (staging / "index.html").is_file():
        shutil.rmtree(staging)
        raise SystemExit(f"{archive} has no index.html; not a web UI bundle.")
    if TARGET.exists():
        TARGET.rename(previous)
    staging.rename(TARGET)
    if previous.exists():
        shutil.rmtree(previous)
    count = sum(1 for p in TARGET.rglob("*") if p.is_file())
    print(f"Installed {count} files from {archive} into {TARGET.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Skip npm and stage whatever is already in frontend/dist",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        help="After staging, also pack the bundle into this zip (release CI)",
    )
    parser.add_argument(
        "--install-archive",
        type=Path,
        help="Skip the build and install the bundle from this zip instead",
    )
    args = parser.parse_args()
    if args.install_archive:
        install_archive(args.install_archive)
        return
    if not args.no_build:
        build_frontend()
    stage()
    if args.archive:
        pack(args.archive)


if __name__ == "__main__":
    main()
