"""Join the per-arch latest-mac.yml feeds electron-builder writes into one.

Each Mac runner builds one architecture and writes a latest-mac.yml listing
only its own files. electron-updater reads a single latest-mac.yml and picks
the arm64 or x64 zip from its `files`, so the release needs both lists.

Usage: python scripts/merge_mac_update_feed.py latest-mac-arm64.yml latest-mac-x86_64.yml
"""

import sys
from pathlib import Path

import yaml


def merge(feeds: list[dict]) -> dict:
    versions = {feed["version"] for feed in feeds}
    if len(versions) != 1:
        raise SystemExit(f"Feeds disagree on the version: {sorted(versions)}")
    merged = dict(feeds[0])
    files: dict[str, dict] = {}
    for feed in feeds:
        for entry in feed.get("files", []):
            files[entry["url"]] = entry
    # Apple silicon first: older electron-updater builds fall back to the
    # first zip, and new Macs are the common case.
    merged["files"] = sorted(files.values(), key=lambda e: "arm64" not in e["url"])
    first = merged["files"][0]
    merged["path"] = first["url"]
    merged["sha512"] = first["sha512"]
    merged["releaseDate"] = max(str(feed.get("releaseDate", "")) for feed in feeds)
    return merged


def main() -> None:
    paths = [Path(arg) for arg in sys.argv[1:]]
    if not paths:
        raise SystemExit(__doc__)
    feeds = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in paths]
    sys.stdout.write(yaml.safe_dump(merge(feeds), sort_keys=False))


if __name__ == "__main__":
    main()
