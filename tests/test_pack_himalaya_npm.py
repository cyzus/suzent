import hashlib
import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts/pack_himalaya_npm.py"
spec = importlib.util.spec_from_file_location("suzent_pack_himalaya_npm", SCRIPT)
pack_himalaya = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pack_himalaya
spec.loader.exec_module(pack_himalaya)


def _archive(member: str, data: bytes) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        info = tarfile.TarInfo(member)
        info.size = len(data)
        bundle.addfile(info, io.BytesIO(data))
        extra = tarfile.TarInfo("share/man/himalaya.1")
        extra.size = 3
        bundle.addfile(extra, io.BytesIO(b"man"))
    return buffer.getvalue()


@pytest.fixture
def fake_release(monkeypatch):
    archives = {}
    for platform, (asset, _digest, member) in pack_himalaya.ARCHIVES.items():
        archives[asset] = _archive(member, f"bin-{platform}".encode())
    licenses = {name: f"{name} text".encode() for name in pack_himalaya.LICENSES}
    monkeypatch.setattr(
        pack_himalaya,
        "ARCHIVES",
        {
            platform: (asset, hashlib.sha256(archives[asset]).hexdigest(), member)
            for platform, (asset, _d, member) in pack_himalaya.ARCHIVES.items()
        },
    )
    monkeypatch.setattr(
        pack_himalaya,
        "LICENSES",
        {name: hashlib.sha256(data).hexdigest() for name, data in licenses.items()},
    )

    def download(url: str) -> bytes:
        name = url.rsplit("/", 1)[-1]
        return archives.get(name) or licenses[name]

    return download


def test_packs_only_the_binary_and_licenses(tmp_path: Path, fake_release):
    packages = pack_himalaya.pack(tmp_path, download=fake_release)

    assert [p.name for p in packages] == [
        "himalaya-darwin-arm64",
        "himalaya-darwin-x64",
        "himalaya-linux-arm64",
        "himalaya-linux-x64",
        "himalaya-win32-x64",
    ]
    linux = tmp_path / "himalaya-linux-x64"
    assert sorted(p.name for p in linux.iterdir()) == [
        "LICENSE-APACHE",
        "LICENSE-MIT",
        "README.md",
        "himalaya",
        "package.json",
    ]
    assert (linux / "himalaya").read_bytes() == b"bin-linux-x64"
    assert (tmp_path / "himalaya-win32-x64" / "himalaya.exe").is_file()
    manifest = json.loads((linux / "package.json").read_text())
    assert manifest["name"] == "@suzent/himalaya-linux-x64"
    assert manifest["version"] == pack_himalaya.VERSION
    assert manifest["license"] == "MIT OR Apache-2.0"


def test_a_changed_release_archive_is_refused(tmp_path: Path, fake_release):
    def tampered(url: str) -> bytes:
        data = fake_release(url)
        return data + b"x" if url.endswith(".tgz") else data

    with pytest.raises(pack_himalaya.PackError, match="expected sha256"):
        pack_himalaya.pack(tmp_path, download=tampered)


def test_pinned_archives_cover_the_platforms_suzent_installs_for():
    assert set(pack_himalaya.ARCHIVES) == {
        "darwin-arm64",
        "darwin-x64",
        "linux-arm64",
        "linux-x64",
        "win32-x64",
    }


def test_bootstrap_packages_are_empty_placeholders(tmp_path: Path):
    packages = pack_himalaya.bootstrap(tmp_path)

    for directory in packages:
        assert sorted(p.name for p in directory.iterdir()) == [
            "README.md",
            "package.json",
        ]
        assert (
            json.loads((directory / "package.json").read_text())["version"] == "0.0.0"
        )
