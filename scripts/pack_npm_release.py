"""Lay out a desktop release's files as npm packages.

npmmirror copies every package on npmjs.com within minutes and without
review, so publishing the release files there gives mainland China a domestic
download source. Each platform gets one package holding its app, its
installer, the web UI bundle and SHA256SUMS:

    python scripts/pack_npm_release.py release-assets v0.18.0 npm-packages

writes ``npm-packages/desktop-<platform>/`` directories ready for
``npm publish``. ``--bootstrap`` writes empty 0.0.0 packages instead, for the
one-time manual publish that lets npm's Trusted Publishing be configured:

    npm login
    python scripts/pack_npm_release.py --bootstrap --publish npm-bootstrap
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCOPE = "@suzent"
REPOSITORY = "https://github.com/cyzus/suzent"
# npm platform name -> the suffix the release assets of that platform carry.
PLATFORMS = {
    "win32-x64": "windows-x86_64",
    "darwin-arm64": "macos-aarch64",
    "darwin-x64": "macos-x86_64",
    "linux-x64": "linux-x86_64",
}
# Platform-independent files every package carries.
SHARED = ("SHA256SUMS", "suzent-webui.zip")
BOOTSTRAP_VERSION = "0.0.0"


def package_name(platform: str) -> str:
    return f"{SCOPE}/desktop-{platform}"


def platform_assets(assets: list[str], suffix: str) -> list[str]:
    """Assets built for ``suffix``, such as ``suzent-macos-aarch64`` and
    ``suzent-installer-macos-aarch64.dmg``."""
    pattern = re.compile(rf"^suzent-(installer-)?{re.escape(suffix)}(\.exe|\.dmg)?$")
    return sorted(name for name in assets if pattern.match(name))


def manifest(platform: str, version: str) -> dict:
    return {
        "name": package_name(platform),
        "version": version,
        "description": f"Suzent desktop release files for {platform}, mirrored for download.",
        "license": "Apache-2.0",
        "homepage": REPOSITORY,
        "repository": {"type": "git", "url": f"git+{REPOSITORY}.git"},
        "publishConfig": {"access": "public"},
    }


def readme(platform: str, files: list[str]) -> str:
    listing = "\n".join(f"- `{name}`" for name in files) or "- (placeholder)"
    return (
        f"# {package_name(platform)}\n\n"
        "The files of a [Suzent](https://github.com/cyzus/suzent) desktop release, "
        "published here so the installer can download them from npm mirrors. "
        "This package has no code to import. To install Suzent, follow the "
        "README on GitHub.\n\n"
        f"{listing}\n"
    )


def write_package(out: Path, platform: str, version: str, sources: list[Path]) -> Path:
    directory = out / f"desktop-{platform}"
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    for source in sources:
        shutil.copy2(source, directory / source.name)
    names = [source.name for source in sources]
    (directory / "package.json").write_text(
        json.dumps(manifest(platform, version), indent=2) + "\n", encoding="utf-8"
    )
    (directory / "README.md").write_text(readme(platform, names), encoding="utf-8")
    return directory


def pack(assets_dir: Path, tag: str, out: Path) -> list[Path]:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError(f"not a stable release tag: {tag}")
    assets = [path.name for path in assets_dir.iterdir() if path.is_file()]
    if "SHA256SUMS" not in assets:
        raise ValueError(f"{assets_dir} has no SHA256SUMS")
    shared = [assets_dir / name for name in SHARED if name in assets]
    packages = []
    for platform, suffix in PLATFORMS.items():
        own = platform_assets(assets, suffix)
        if not own:
            raise ValueError(f"no release assets for {suffix}")
        sources = [assets_dir / name for name in own] + shared
        packages.append(write_package(out, platform, tag[1:], sources))
    return packages


def bootstrap(out: Path) -> list[Path]:
    return [
        write_package(out, platform, BOOTSTRAP_VERSION, []) for platform in PLATFORMS
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "assets", nargs="?", type=Path, help="downloaded release assets"
    )
    parser.add_argument("tag", nargs="?", help="release tag, such as v0.18.0")
    parser.add_argument("out", type=Path, help="directory to write the packages into")
    parser.add_argument(
        "--bootstrap", action="store_true", help="write empty 0.0.0 packages"
    )
    parser.add_argument(
        "--publish", action="store_true", help="run npm publish in each package"
    )
    args = parser.parse_args(argv)
    if args.bootstrap:
        packages = bootstrap(args.out)
    elif args.assets is None or args.tag is None:
        parser.error("assets and tag are required unless --bootstrap is given")
    else:
        try:
            packages = pack(args.assets, args.tag, args.out)
        except ValueError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
    for directory in packages:
        print(directory)
    if args.publish:
        npm = shutil.which("npm")
        if npm is None:
            print("error: npm is not installed", file=sys.stderr)
            return 1
        for directory in packages:
            # Prompts for your two-factor code on the first package.
            subprocess.run(
                [npm, "publish", "--access", "public"], cwd=directory, check=True
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
