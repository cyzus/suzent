"""Repackage himalaya's release binaries as npm packages.

The email plugin runs the himalaya CLI (MIT OR Apache-2.0, by Pimalaya).
Suzent downloads plugin programs from npm, which npmmirror copies without
review, so publishing them as ``@suzent/himalaya-<platform>`` gives mainland
China a domestic source. Each GitHub release archive is checked against the
SHA-256 pinned below before anything is packed:

    python scripts/pack_himalaya_npm.py npm-himalaya

writes ``npm-himalaya/himalaya-<platform>/`` directories ready for
``npm publish``. ``--bootstrap`` writes empty 0.0.0 packages instead, for the
one-time manual publish that lets npm's Trusted Publishing be configured:

    npm login
    python scripts/pack_himalaya_npm.py --bootstrap --publish npm-bootstrap
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

SCOPE = "@suzent"
VERSION = "2.2.1"
UPSTREAM = "https://github.com/pimalaya/himalaya"
REPOSITORY = "https://github.com/cyzus/suzent"
BOOTSTRAP_VERSION = "0.0.0"
# npm platform -> (release archive, its SHA-256, the binary inside it).
ARCHIVES = {
    "darwin-arm64": (
        "himalaya.aarch64-darwin.tgz",
        "a5d97a1f7bbca45e58bddde3f9f17325f614c9cd6d5f17fabf38ddcb030869ab",
        "himalaya",
    ),
    "darwin-x64": (
        "himalaya.x86_64-darwin.tgz",
        "24e226bc6bccfeadc89608953ffc0fcb46623d1d4cd4689734cbace243cc8d2e",
        "himalaya",
    ),
    "linux-arm64": (
        "himalaya.aarch64-linux.tgz",
        "1dc21c3dd6d948929e22e5cae49b9d0b3b30ff88fafd4493fd4460c6252e9d90",
        "himalaya",
    ),
    "linux-x64": (
        "himalaya.x86_64-linux.tgz",
        "5c5ba2724c162f82d0a0c71b6c03224ed44f8bef7b14ace5da0635d3af2665a0",
        "himalaya",
    ),
    "win32-x64": (
        "himalaya.x86_64-windows.tgz",
        "abea8ecbca5fbd566860941bbab91e40f1dde57e737091a451208b8c61b99523",
        "himalaya.exe",
    ),
}
LICENSES = {
    "LICENSE-MIT": "94bc721fc860b328c7e46cd6fbd8abe272de507af391c40ce51e68ddb0fd098e",
    "LICENSE-APACHE": "9998ecba2c76365fb29ae8ff233b16927b1fb88fad7d1f1a8e7d0e93ae791769",
}


class PackError(Exception):
    pass


def package_name(platform: str) -> str:
    return f"{SCOPE}/himalaya-{platform}"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "suzent-release"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def verified(data: bytes, expected: str, what: str) -> bytes:
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise PackError(f"{what}: expected sha256 {expected}, got {actual}")
    return data


def binary_from_archive(archive: bytes, member: str) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        try:
            info = bundle.getmember(member)
        except KeyError as exc:
            raise PackError(f"archive has no {member}") from exc
        if not info.isfile():
            raise PackError(f"{member} is not a regular file")
        data = bundle.extractfile(info)
        assert data is not None
        return data.read()


def manifest(platform: str, version: str) -> dict:
    os_name, cpu = platform.split("-")
    return {
        "name": package_name(platform),
        "version": version,
        "description": f"The himalaya email CLI for {platform}, repackaged for Suzent.",
        "license": "MIT OR Apache-2.0",
        "homepage": REPOSITORY,
        "repository": {"type": "git", "url": f"git+{REPOSITORY}.git"},
        "os": [os_name],
        "cpu": [cpu],
        "publishConfig": {"access": "public"},
    }


def readme(platform: str, version: str) -> str:
    return (
        f"# {package_name(platform)}\n\n"
        f"The [himalaya]({UPSTREAM}) {version} command-line email client for "
        f"{platform}, unchanged from its GitHub release and published here so "
        "[Suzent](https://github.com/cyzus/suzent) can download it from npm "
        "mirrors. himalaya is by Pimalaya and licensed MIT OR Apache-2.0; see "
        "the license files in this package. This package has no code to import.\n"
    )


def write_package(
    out: Path,
    platform: str,
    version: str,
    files: dict[str, bytes],
) -> Path:
    directory = out / f"himalaya-{platform}"
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    for name, data in files.items():
        path = directory / name
        path.write_bytes(data)
        if name.startswith("himalaya"):
            path.chmod(0o755)
    (directory / "package.json").write_text(
        json.dumps(manifest(platform, version), indent=2) + "\n", encoding="utf-8"
    )
    (directory / "README.md").write_text(readme(platform, version), encoding="utf-8")
    return directory


def pack(out: Path, download=fetch) -> list[Path]:
    licenses = {
        name: verified(
            download(
                f"https://raw.githubusercontent.com/pimalaya/himalaya/v{VERSION}/{name}"
            ),
            digest,
            name,
        )
        for name, digest in LICENSES.items()
    }
    packages = []
    for platform, (asset, digest, member) in ARCHIVES.items():
        url = f"{UPSTREAM}/releases/download/v{VERSION}/{asset}"
        archive = verified(download(url), digest, asset)
        files = {member: binary_from_archive(archive, member), **licenses}
        packages.append(write_package(out, platform, VERSION, files))
    return packages


def bootstrap(out: Path) -> list[Path]:
    return [
        write_package(out, platform, BOOTSTRAP_VERSION, {}) for platform in ARCHIVES
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path, help="directory to write the packages into")
    parser.add_argument(
        "--bootstrap", action="store_true", help="write empty 0.0.0 packages"
    )
    parser.add_argument(
        "--publish", action="store_true", help="run npm publish in each package"
    )
    args = parser.parse_args(argv)
    try:
        packages = bootstrap(args.out) if args.bootstrap else pack(args.out)
    except PackError as error:
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
