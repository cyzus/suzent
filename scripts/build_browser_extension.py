"""Package extensions/browser as a store-ready ZIP.

    uv run --no-sync python scripts/build_browser_extension.py

The archive holds only the extension directory's own contents, with
manifest.json at the ZIP root, as both stores require. Entries are sorted and
given a fixed timestamp so the same sources always produce byte-identical
output - a rebuild can be compared against what was uploaded.
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extensions/browser"
OUTPUT_DIR = ROOT / "store-upload"

# Chrome rejects an upload whose manifest omits any of these, and a ZIP that
# silently lost one still installs unpacked - so the check belongs here.
REQUIRED = ("manifest.json", "worker.js", "pair.js", "popup.html")
EXCLUDED_NAMES = {".DS_Store", "Thumbs.db", "__MACOSX"}
VERSION_PATTERN = re.compile(r"^\d+\.\d+(\.\d+){0,2}$")
# Zip epoch: 1980-01-01. Anything earlier is unrepresentable.
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def read_version() -> str:
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    version = manifest.get("version", "")
    if not VERSION_PATTERN.match(version):
        raise SystemExit(f"manifest.json has an invalid version: {version!r}")
    return version


def as_tuple(version: str) -> tuple[int, ...]:
    """Chrome allows one to four dot-separated integers, so pad before comparing."""
    parts = tuple(int(part) for part in version.split("."))
    return parts + (0,) * (4 - len(parts))


def sources() -> list[Path]:
    found = sorted(
        path
        for path in EXTENSION.rglob("*")
        if path.is_file()
        and not any(
            part in EXCLUDED_NAMES or part.startswith(".")
            for part in path.relative_to(EXTENSION).parts
        )
    )
    names = {path.relative_to(EXTENSION).as_posix() for path in found}
    missing = [name for name in REQUIRED if name not in names]
    if missing:
        raise SystemExit(
            f"Extension source is incomplete, missing: {', '.join(missing)}"
        )
    return found


def build(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sources():
            info = zipfile.ZipInfo(path.relative_to(EXTENSION).as_posix(), FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Destination ZIP path")
    parser.add_argument(
        "--print-version",
        action="store_true",
        help="Print the manifest version and exit",
    )
    parser.add_argument(
        "--newer-than",
        metavar="VERSION",
        help="Fail unless the manifest version is strictly greater than VERSION",
    )
    args = parser.parse_args()

    version = read_version()
    if args.newer_than is not None:
        if not VERSION_PATTERN.match(args.newer_than):
            raise SystemExit(f"Not a version to compare against: {args.newer_than!r}")
        # Strictly greater, not merely different: the stores reject a downgrade,
        # and a version that only differs can still be one already spent.
        if as_tuple(version) <= as_tuple(args.newer_than):
            raise SystemExit(
                f"Extension version {version} must be greater than {args.newer_than}."
            )
        print(f"{args.newer_than} -> {version}")
        return
    if args.print_version:
        print(version)
        return

    destination = args.output or OUTPUT_DIR / f"suzent-browser-{version}.zip"
    build(destination)
    print(
        f"{destination.relative_to(ROOT) if destination.is_relative_to(ROOT) else destination}"
    )


if __name__ == "__main__":
    main()
