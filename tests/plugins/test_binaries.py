"""Programs plugins declare in plugin.yaml, installed from pinned npm tarballs."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from suzent.plugins import PluginManager, binaries
from suzent.plugins.binaries import BinaryInstallError, BinarySpec


def _tarball(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(f"package/{name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


TARBALL = _tarball(
    {
        "bin/tool-linux-x64": b"#!/bin/sh\necho tool 1.0.0\n",
        "bin/helper-linux-x64": b"helper",
        "bin/tool-darwin-arm64": b"mac",
        "package.json": b"{}",
    }
)


def _spec(sha256: str | None = None, **extra) -> BinarySpec:
    return BinarySpec.model_validate(
        {
            "name": "tool",
            "version": "1.0.0",
            "package": "@acme/tool",
            "sha256": sha256 or hashlib.sha256(TARBALL).hexdigest(),
            "env": "ACME_TOOL_BIN",
            "platforms": {
                "linux-x64": {
                    "files": {
                        "tool": "bin/tool-linux-x64",
                        "tool-helper": "bin/helper-linux-x64",
                    }
                },
                "darwin-arm64": {"files": {"tool": "bin/tool-darwin-arm64"}},
            },
            **extra,
        }
    )


class FakeSource(binaries.TarballSource):
    def __init__(self, payloads: dict[str, bytes | Exception]) -> None:
        self.payloads = payloads
        self.requested: list[str] = []

    def download(self, url: str, max_bytes: int) -> bytes:
        self.requested.append(url)
        payload = self.payloads.get(url, OSError("not found"))
        if isinstance(payload, Exception):
            raise payload
        return payload


@pytest.fixture(autouse=True)
def _outside_china(monkeypatch):
    monkeypatch.setattr("suzent.network_region.china_mode", lambda: False)
    monkeypatch.delenv("ACME_TOOL_BIN", raising=False)


NPM = "https://registry.npmjs.org/@acme/tool/-/tool-1.0.0.tgz"
MIRROR = "https://registry.npmmirror.com/@acme/tool/-/tool-1.0.0.tgz"


def test_tarball_urls_put_npmmirror_first_in_china(monkeypatch):
    assert binaries.tarball_urls("@acme/tool", "1.0.0") == [NPM, MIRROR]
    monkeypatch.setattr("suzent.network_region.china_mode", lambda: True)
    assert binaries.tarball_urls("@acme/tool", "1.0.0") == [MIRROR, NPM]


def test_install_takes_only_the_listed_files(tmp_path: Path):
    root = tmp_path / "tool" / "1.0.0"
    result = binaries.install(
        "acme",
        _spec(),
        source=FakeSource({NPM: TARBALL}),
        root=root,
        platform_key="linux-x64",
    )

    assert sorted(path.name for path in root.iterdir()) == [
        "install.json",
        "tool",
        "tool-helper",
    ]
    assert (root / "tool").read_bytes().startswith(b"#!/bin/sh")
    assert os.access(root / "tool", os.X_OK)
    assert result["downloadedFrom"] == NPM
    recorded = json.loads((root / "install.json").read_text())
    assert recorded["sha256"] == hashlib.sha256(TARBALL).hexdigest()


def test_install_falls_back_to_the_other_registry(tmp_path: Path):
    source = FakeSource({NPM: OSError("blocked"), MIRROR: TARBALL})

    result = binaries.install(
        "acme", _spec(), source=source, root=tmp_path / "t", platform_key="linux-x64"
    )

    assert source.requested == [NPM, MIRROR]
    assert result["downloadedFrom"] == MIRROR


def test_checksum_mismatch_installs_nothing_and_stops(tmp_path: Path):
    source = FakeSource({NPM: TARBALL + b"x", MIRROR: TARBALL})
    root = tmp_path / "tool" / "1.0.0"

    with pytest.raises(BinaryInstallError, match="Checksum mismatch"):
        binaries.install(
            "acme", _spec(), source=source, root=root, platform_key="linux-x64"
        )

    assert source.requested == [NPM]
    assert not (tmp_path / "tool").exists()


def test_a_missing_file_in_the_tarball_installs_nothing(tmp_path: Path):
    spec = _spec(
        platforms={"linux-x64": {"files": {"tool": "bin/not-there"}}},
    )
    root = tmp_path / "tool" / "1.0.0"

    with pytest.raises(BinaryInstallError, match="does not contain"):
        binaries.install(
            "acme",
            spec,
            source=FakeSource({NPM: TARBALL}),
            root=root,
            platform_key="linux-x64",
        )
    assert not root.exists()


def test_unsupported_platform_is_refused_before_downloading(tmp_path: Path):
    source = FakeSource({NPM: TARBALL})

    with pytest.raises(BinaryInstallError, match="not built for"):
        binaries.install(
            "acme", _spec(), source=source, root=tmp_path, platform_key="win32-x64"
        )
    assert source.requested == []


@pytest.mark.parametrize(
    "files",
    [
        {"tool": "../escape"},
        {"tool": "/etc/passwd"},
        {"../tool": "bin/tool-linux-x64"},
        {"sub/tool": "bin/tool-linux-x64"},
    ],
)
def test_manifest_rejects_unsafe_paths(files):
    with pytest.raises(ValidationError):
        _spec(platforms={"linux-x64": {"files": files}})


def test_every_platform_needs_a_package_and_a_hash():
    with pytest.raises(ValidationError, match="no sha256"):
        BinarySpec.model_validate(
            {
                "name": "tool",
                "version": "1.0.0",
                "package": "@acme/tool",
                "platforms": {"linux-x64": {"files": {"tool": "tool"}}},
            }
        )
    per_platform = BinarySpec.model_validate(
        {
            "name": "tool",
            "version": "1.0.0",
            "platforms": {
                "linux-x64": {
                    "package": "@acme/tool-linux-x64",
                    "sha256": "a" * 64,
                    "files": {"tool": "tool"},
                }
            },
        }
    )
    entry = per_platform.for_platform("linux-x64")
    assert per_platform.package_for(entry) == "@acme/tool-linux-x64"
    assert per_platform.sha256_for(entry) == "a" * 64


def test_locate_prefers_the_override_then_suzent_copy_then_path(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("suzent.config.paths.DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(binaries, "current_platform", lambda: "linux-x64")
    on_path = tmp_path / "path" / "tool"
    on_path.parent.mkdir()
    on_path.write_text("")
    on_path.chmod(0o755)
    monkeypatch.setattr(
        "shutil.which", lambda name: str(on_path) if name == "tool" else None
    )
    spec = _spec()

    assert binaries.locate("acme", spec) == (on_path, "path")

    binaries.install("acme", spec, source=FakeSource({NPM: TARBALL}))
    managed = binaries.install_dir("acme", spec) / "tool"
    assert binaries.locate("acme", spec) == (managed, "managed")

    monkeypatch.setenv("ACME_TOOL_BIN", str(on_path))
    assert binaries.locate("acme", spec) == (on_path, "override")
    monkeypatch.setenv("ACME_TOOL_BIN", str(tmp_path / "missing"))
    assert binaries.locate("acme", spec) is None


def _plugin_dir(tmp_path: Path) -> Path:
    plugin = tmp_path / "plugins" / "acme"
    plugin.mkdir(parents=True)
    plugin.joinpath("plugin.yaml").write_text(
        json.dumps(
            {
                "id": "acme",
                "api_version": 3,
                "binaries": [_spec().model_dump(exclude_none=True)],
            }
        )
    )
    return plugin.parent


def test_plugin_list_reports_binary_status_without_downloading(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("suzent.config.paths.DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(binaries, "current_platform", lambda: "linux-x64")
    monkeypatch.setattr("shutil.which", lambda _name: None)
    manager = PluginManager(
        [_plugin_dir(tmp_path)], tmp_path / "plugins.json", entry_point_group=None
    )

    described = manager.discover()["acme"].to_dict()["binaries"]

    assert described == [
        {
            "name": "tool",
            "version": "1.0.0",
            "package": "@acme/tool",
            "supported": True,
            "installed": False,
            "path": None,
            "source": None,
            "env": "ACME_TOOL_BIN",
            "notice": "",
        }
    ]


def test_install_route_needs_confirmation(tmp_path: Path, monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient

    import suzent.plugins.manager as manager_module
    from suzent.routes import plugin_routes

    manager = PluginManager(
        [_plugin_dir(tmp_path)], tmp_path / "plugins.json", entry_point_group=None
    )
    monkeypatch.setattr(manager_module, "_manager", manager, raising=False)
    installed: list[str] = []
    monkeypatch.setattr(
        binaries,
        "install",
        lambda plugin_id, spec: installed.append(spec.name) or {"installed": True},
    )
    client = TestClient(
        Starlette(
            routes=[
                Route(
                    "/plugins/{name}/binaries/{binary}/install",
                    plugin_routes.install_binary,
                    methods=["POST"],
                )
            ]
        )
    )

    assert (
        client.post("/plugins/acme/binaries/tool/install", json={}).status_code == 400
    )
    assert installed == []
    assert client.post("/plugins/acme/binaries/nope/install").status_code == 404
    assert client.post("/plugins/nope/binaries/tool/install").status_code == 404
    response = client.post(
        "/plugins/acme/binaries/tool/install", json={"confirmed": True}
    )
    assert response.status_code == 200
    assert installed == ["tool"]


def test_concurrent_installs_download_once(tmp_path: Path):
    import threading

    started = threading.Event()
    release = threading.Event()

    class SlowSource(FakeSource):
        def download(self, url: str, max_bytes: int) -> bytes:
            started.set()
            release.wait(5)
            return super().download(url, max_bytes)

    source = SlowSource({NPM: TARBALL})
    root = tmp_path / "tool" / "1.0.0"
    results: list[dict] = []

    def run() -> None:
        results.append(
            binaries.install(
                "acme", _spec(), source=source, root=root, platform_key="linux-x64"
            )
        )

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    started.wait(5)
    release.set()
    for thread in threads:
        thread.join(10)

    assert len(results) == 2
    assert source.requested == [NPM]
    assert (root / "tool").is_file()
