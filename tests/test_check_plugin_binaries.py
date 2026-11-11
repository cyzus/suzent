import base64
import hashlib
import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts/check_plugin_binaries.py"
spec = importlib.util.spec_from_file_location("suzent_check_plugin_binaries", SCRIPT)
check = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = check
spec.loader.exec_module(check)

OLD = "2026-01-01T00:00:00.000Z"
NEW = "2999-01-01T00:00:00.000Z"
PUBLISHER = {"_npmUser": {"trustedPublisher": {"id": "github", "oidcConfigId": "a"}}}


def _tarball(files: list[str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        for name in files:
            info = tarfile.TarInfo(f"package/{name}")
            info.size = 1
            bundle.addfile(info, io.BytesIO(b"x"))
    return buffer.getvalue()


class Registry:
    def __init__(self) -> None:
        self.urls: dict[str, bytes] = {}

    def package(
        self,
        name: str,
        releases: dict[str, str],
        files: list[str],
        publishers: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        versions, hashes = {}, {}
        for version in releases:
            payload = _tarball(files + [f"{name}-{version}"])
            tarball = f"https://registry.example/{name}-{version}.tgz"
            integrity = base64.b64encode(hashlib.sha512(payload).digest()).decode()
            meta = {
                **((publishers or {}).get(version) or PUBLISHER),
                "dist": {
                    "tarball": tarball,
                    "integrity": f"sha512-{integrity}",
                    "attestations": {"url": "x"},
                },
            }
            versions[version] = meta
            self.urls[tarball] = payload
            self.urls[f"{check.REGISTRY}/{name.replace('/', '%2F')}/{version}"] = (
                json.dumps(meta).encode()
            )
            hashes[version] = hashlib.sha256(payload).hexdigest()
        self.urls[f"{check.REGISTRY}/{name.replace('/', '%2F')}"] = json.dumps(
            {"versions": versions, "time": releases}
        ).encode()
        return hashes

    def fetch(self, url: str) -> bytes:
        return self.urls[url]


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> Registry:
    fake = Registry()
    monkeypatch.setattr(check, "fetch", fake.fetch)
    return fake


def test_single_package_moves_to_newest_old_enough_release(
    tmp_path: Path, registry: Registry
) -> None:
    hashes = registry.package(
        "tool",
        {"1.0.0": OLD, "1.1.0": OLD, "1.2.0": NEW, "2.0.0-rc.1": OLD},
        ["bin/tool-linux"],
    )
    manifest = tmp_path / "plugin.yaml"
    manifest.write_text(
        "version: 1.0.0\n"
        "binaries:\n"
        "  - name: tool\n"
        "    version: 1.0.0\n"
        "    package: tool\n"
        "    # pinned tarball\n"
        f"    sha256: {hashes['1.0.0']}\n"
        "    max_bytes: 1000000\n"
        "    platforms:\n"
        "      linux-x64:\n"
        "        files:\n"
        "          tool: bin/tool-linux\n"
    )

    [update] = check.check_manifest(manifest, min_age_days=7)

    assert (update.old, update.new) == ("1.0.0", "1.1.0")
    text = manifest.read_text()
    assert text.startswith("version: 1.0.0\n")
    assert "    version: 1.1.0\n" in text
    assert hashes["1.1.0"] in text and hashes["1.0.0"] not in text
    assert "# pinned tarball" in text


def test_a_new_publisher_is_refused(tmp_path: Path, registry: Registry) -> None:
    other = {"_npmUser": {"name": "someone-else"}}
    hashes = registry.package(
        "tool", {"1.0.0": OLD, "1.1.0": OLD}, ["bin/t"], {"1.1.0": other}
    )
    manifest = tmp_path / "plugin.yaml"
    manifest.write_text(
        "binaries:\n  - name: tool\n    version: 1.0.0\n    package: tool\n"
        f"    sha256: {hashes['1.0.0']}\n    max_bytes: 1000000\n"
        "    platforms:\n      linux-x64:\n        files:\n          t: bin/t\n"
    )

    with pytest.raises(check.CheckError, match="different npm publisher"):
        check.check_manifest(manifest, min_age_days=7)


def test_platform_packages_wait_until_all_are_published(
    tmp_path: Path, registry: Registry
) -> None:
    a = registry.package("@s/t-a", {"1.0.0": OLD, "1.1.0": OLD}, ["t"])
    b = registry.package("@s/t-b", {"1.0.0": OLD}, ["t"])
    manifest = tmp_path / "plugin.yaml"
    body = (
        "binaries:\n  - name: t\n    version: 1.0.0\n    max_bytes: 1000000\n"
        "    platforms:\n"
        f'      a:\n        package: "@s/t-a"\n        sha256: {a["1.0.0"]}\n'
        "        files:\n          t: t\n"
        f'      b:\n        package: "@s/t-b"\n        sha256: {b["1.0.0"]}\n'
        "        files:\n          t: t\n"
    )
    manifest.write_text(body)

    assert check.check_manifest(manifest, min_age_days=7) == []
    assert manifest.read_text() == body

    b = registry.package("@s/t-b", {"1.0.0": OLD, "1.1.0": OLD}, ["t"])
    [update] = check.check_manifest(manifest, min_age_days=7)

    assert update.new == "1.1.0"
    assert a["1.1.0"] in manifest.read_text() and b["1.1.0"] in manifest.read_text()


def test_himalaya_upstream_rewrites_the_pack_script(
    tmp_path: Path, registry: Registry, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "pack.py"
    script.write_text(
        'VERSION = "2.2.1"\n'
        'ARCHIVES = {"linux-x64": ("h.tgz", "' + "a" * 64 + '", "himalaya")}\n'
        'LICENSES = {"LICENSE-MIT": "' + "b" * 64 + '"}\n'
    )
    monkeypatch.setattr(check, "PACK_SCRIPT", script)
    registry.urls["https://api.github.com/repos/pimalaya/himalaya/releases/latest"] = (
        json.dumps(
            {
                "tag_name": "v2.3.0",
                "published_at": OLD,
                "assets": [{"name": "h.tgz", "browser_download_url": "https://dl/h"}],
            }
        ).encode()
    )
    registry.urls["https://dl/h"] = b"archive"
    registry.urls[
        "https://raw.githubusercontent.com/pimalaya/himalaya/v2.3.0/LICENSE-MIT"
    ] = b"mit"

    [update] = check.check_himalaya_upstream(min_age_days=7)

    assert (update.old, update.new) == ("2.2.1", "2.3.0")
    text = script.read_text()
    assert 'VERSION = "2.3.0"' in text
    assert hashlib.sha256(b"archive").hexdigest() in text
    assert hashlib.sha256(b"mit").hexdigest() in text
