"""Find newer releases of the programs plugins pin, and update the pins.

Each ``plugins/*/plugin.yaml`` pins its programs to an npm version and the
SHA-256 of that tarball. This script looks for a newer release of each, then
downloads it, checks it the way the installer would, and rewrites the pin. It
also follows himalaya upstream, which ``scripts/pack_himalaya_npm.py``
repackages for npm before the email plugin can use it.

A release is taken only when it is at least ``--min-age-days`` old and, on
npm, comes from the same trusted publisher as the pinned one. The scheduled
``check-plugin-binaries`` workflow turns the changes into a pull request;
nothing here publishes or merges anything.

Usage: python scripts/check_plugin_binaries.py [--summary FILE] [--min-age-days N]
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
import tarfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACK_SCRIPT = ROOT / "scripts" / "pack_himalaya_npm.py"
REGISTRY = "https://registry.npmjs.org"
USER_AGENT = "suzent-plugin-binary-check"
_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class CheckError(Exception):
    pass


@dataclass
class Update:
    title: str
    old: str
    new: str
    notes: list[str] = field(default_factory=list)


def fetch(url: str) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def fetch_json(url: str) -> Any:
    return json.loads(fetch(url))


def version_key(version: str) -> tuple[int, int, int] | None:
    match = _VERSION.fullmatch(version)
    if not match:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def is_newer(candidate: str, current: str) -> bool:
    new, old = version_key(candidate), version_key(current)
    return new is not None and old is not None and new > old


def old_enough(published: str, min_age_days: int) -> bool:
    when = dt.datetime.fromisoformat(published.replace("Z", "+00:00"))
    return dt.datetime.now(dt.UTC) - when >= dt.timedelta(days=min_age_days)


def publisher(meta: dict[str, Any]) -> Any:
    user = meta.get("_npmUser") or {}
    return user.get("trustedPublisher") or user.get("name")


def npm_candidate(package: str, current: str, min_age_days: int) -> str | None:
    """The newest stable release past ``current`` that is old enough."""
    doc = fetch_json(f"{REGISTRY}/{package.replace('/', '%2F')}")
    times = doc.get("time", {})
    candidates = [
        version
        for version in doc.get("versions", {})
        if is_newer(version, current)
        and version in times
        and old_enough(times[version], min_age_days)
    ]
    if not candidates:
        return None
    newest = max(candidates, key=version_key)
    pinned, chosen = doc["versions"].get(current, {}), doc["versions"][newest]
    if publisher(pinned) != publisher(chosen):
        raise CheckError(
            f"{package} {newest} has a different npm publisher than {current}"
        )
    if not chosen.get("dist", {}).get("attestations"):
        raise CheckError(f"{package} {newest} has no npm provenance attestation")
    return newest


def verified_tarball(
    package: str, version: str, max_bytes: int, files: list[str]
) -> str:
    """Download one tarball, check the files the plugin needs, return its sha256."""
    meta = fetch_json(f"{REGISTRY}/{package.replace('/', '%2F')}/{version}")
    payload = fetch(meta["dist"]["tarball"])
    if len(payload) > max_bytes:
        raise CheckError(
            f"{package}@{version} is {len(payload)} bytes, over max_bytes {max_bytes}"
        )
    integrity = meta["dist"].get("integrity", "")
    if integrity.startswith("sha512-"):
        expected = base64.b64decode(integrity.removeprefix("sha512-"))
        if hashlib.sha512(payload).digest() != expected:
            raise CheckError(f"{package}@{version} does not match its npm integrity")
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        names = set(archive.getnames())
    missing = [name for name in files if f"package/{name}" not in names]
    if missing:
        raise CheckError(f"{package}@{version} lacks {', '.join(missing)}")
    return hashlib.sha256(payload).hexdigest()


def _files(entry: dict[str, Any]) -> list[str]:
    return list((entry.get("files") or {}).values())


def check_manifest(path: Path, min_age_days: int) -> list[Update]:
    text = path.read_text(encoding="utf-8")
    manifest = yaml.safe_load(text)
    updates = []
    for spec in manifest.get("binaries") or []:
        current = str(spec["version"])
        platforms: dict[str, Any] = spec.get("platforms") or {}
        max_bytes = int(spec["max_bytes"])
        replacements: dict[str, str] = {}
        if spec.get("package"):
            package = spec["package"]
            new = npm_candidate(package, current, min_age_days)
            if not new:
                continue
            needed = sorted({f for entry in platforms.values() for f in _files(entry)})
            replacements[spec["sha256"]] = verified_tarball(
                package, new, max_bytes, needed
            )
        else:
            news = {
                npm_candidate(entry["package"], current, min_age_days)
                for entry in platforms.values()
            }
            if news == {None}:
                continue
            if len(news) != 1:
                print(
                    f"{path.parent.name}/{spec['name']}: platform packages are not "
                    "all on the same newer version yet; skipping",
                    file=sys.stderr,
                )
                continue
            new = news.pop()
            assert new is not None
            for entry in platforms.values():
                replacements[entry["sha256"]] = verified_tarball(
                    entry["package"], new, max_bytes, _files(entry)
                )
        pattern = re.compile(
            rf"^(\s+version:\s*){re.escape(current)}\s*$", re.MULTILINE
        )
        text, count = pattern.subn(rf"\g<1>{new}", text, count=1)
        if count != 1:
            raise CheckError(f"{path}: could not find version {current} to replace")
        for old_sha, new_sha in replacements.items():
            if text.count(old_sha) != 1:
                raise CheckError(f"{path}: sha256 {old_sha} is not unique")
            text = text.replace(old_sha, new_sha)
        updates.append(
            Update(f"{path.parent.name} plugin: {spec['name']}", current, new)
        )
    if updates:
        path.write_text(text, encoding="utf-8")
    return updates


def _load_pack_script() -> Any:
    spec = importlib.util.spec_from_file_location("pack_himalaya_npm", PACK_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_himalaya_upstream(min_age_days: int) -> list[Update]:
    pack = _load_pack_script()
    release = fetch_json(
        "https://api.github.com/repos/pimalaya/himalaya/releases/latest"
    )
    new = str(release["tag_name"]).removeprefix("v")
    if not is_newer(new, pack.VERSION) or not old_enough(
        release["published_at"], min_age_days
    ):
        return []
    text = PACK_SCRIPT.read_text(encoding="utf-8")
    assets = {asset["name"]: asset for asset in release.get("assets", [])}
    for archive, old_sha, _binary in pack.ARCHIVES.values():
        if archive not in assets:
            raise CheckError(f"himalaya {new} has no release asset {archive}")
        digest = hashlib.sha256(fetch(assets[archive]["browser_download_url"]))
        text = text.replace(old_sha, digest.hexdigest())
    for name, old_sha in pack.LICENSES.items():
        url = f"https://raw.githubusercontent.com/pimalaya/himalaya/v{new}/{name}"
        text = text.replace(old_sha, hashlib.sha256(fetch(url)).hexdigest())
    text = text.replace(f'VERSION = "{pack.VERSION}"', f'VERSION = "{new}"', 1)
    PACK_SCRIPT.write_text(text, encoding="utf-8")
    return [
        Update(
            "himalaya upstream (npm repackage)",
            pack.VERSION,
            new,
            [
                "Merging publishes `@suzent/himalaya-<platform>` to npm. A later "
                "run then moves the email plugin's pin to it."
            ],
        )
    ]


def write_declaration(updates: list[Update]) -> None:
    pinned = [u for u in updates if "plugin:" in u.title]
    if not pinned:
        return
    names = ", ".join(f"{u.title.split(': ', 1)[1]} {u.new}" for u in pinned)
    slug = re.sub(r"[^a-z0-9]+", "-", names.lower()).strip("-")
    declaration = {
        "products": {"desktop": "patch"},
        "summary": f"Plugins now install {names}.",
    }
    path = ROOT / ".releases" / "changes" / f"plugin-binaries-{slug}.json"
    path.write_text(json.dumps(declaration) + "\n", encoding="utf-8")


def summary(updates: list[Update]) -> str:
    lines = [
        "New releases of programs that plugins pin, each at least a week old. npm "
        "packages come from the same trusted publisher as before, with provenance, "
        "and match their npm integrity hash. The new SHA-256 values are in the diff.",
        "",
    ]
    for update in updates:
        lines.append(f"- **{update.title}**: {update.old} → {update.new}")
        lines += [f"  {note}" for note in update.notes]
    lines += [
        "",
        "Before merging, read the release notes for new or changed commands that "
        "the plugin should support. Checks do not start on a pull request opened "
        "by this workflow; close and reopen it to run them.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--summary", type=Path, help="write a PR body here")
    parser.add_argument("--min-age-days", type=int, default=7)
    args = parser.parse_args(argv)
    updates: list[Update] = []
    for manifest in sorted((ROOT / "plugins").glob("*/plugin.yaml")):
        updates += check_manifest(manifest, args.min_age_days)
    updates += check_himalaya_upstream(args.min_age_days)
    if not updates:
        print("All plugin programs are on their newest eligible release.")
        return 0
    write_declaration(updates)
    body = summary(updates)
    print(body)
    if args.summary:
        args.summary.write_text(body, encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CheckError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
