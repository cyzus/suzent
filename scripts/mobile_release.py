"""Validate an immutable mobile release and prepare build metadata and notes."""

import argparse
import json
import re
import subprocess
from pathlib import Path

try:
    from .generate_mobile_version import version_outputs
except ImportError:
    from generate_mobile_version import version_outputs

ROOT = Path(__file__).resolve().parents[1]


def release_metadata(root: Path, tag: str) -> dict[str, str | int]:
    if not re.fullmatch(r"mobile-v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", tag):
        raise ValueError("Expected a mobile-vMAJOR.MINOR.PATCH tag")
    version = json.loads((root / "packages/mobile-contract/version.json").read_text())
    if tag != f"mobile-v{version['version']}":
        raise ValueError("Tag does not match the mobile version")
    version_outputs(root)
    # A separate range avoids collisions with existing developer-preview builds.
    build = 100_000 + version["build"]
    version_outputs(root, build)
    changelog = (root / "packages/mobile-contract/CHANGELOG.md").read_text()
    match = re.search(
        rf"^## \[{re.escape(tag)}\][^\n]*\n(.*?)(?=^## |\Z)", changelog, re.M | re.S
    )
    if not match or not match[1].strip():
        raise ValueError("Mobile changelog must contain release notes for this tag")
    return {
        "version": version["version"],
        "build": build,
        "notes": match[1].strip() + "\n",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tagged = subprocess.check_output(
        ["git", "rev-parse", f"refs/tags/{args.tag}^{{commit}}"], cwd=ROOT, text=True
    ).strip()
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if tagged != head:
        raise SystemExit("Checkout must match the exact release tag")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", head, "origin/main"],
        cwd=ROOT,
        check=True,
    )
    data = release_metadata(ROOT, args.tag)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "notes.md").write_text(str(data.pop("notes")))
    (args.output / "metadata.json").write_text(json.dumps(data) + "\n")


if __name__ == "__main__":
    main()
