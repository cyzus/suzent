"""Consented agent-desktop install, with the network replaced by fixtures."""

from __future__ import annotations

import hashlib
import io
import stat
import tarfile
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.tools.desktop import install, runner
from suzent.tools.desktop.install import (
    CONSENT_TEXT,
    DesktopInstallError,
    install_release,
)
from suzent.tools.desktop.routes import desktop_runtime, desktop_runtime_install

ASSET = "agent-desktop-v1.0.2-test.tar.gz"


class FakeRelease:
    def __init__(
        self, archive: bytes, *, include_asset: bool = True, digest: str | None = None
    ):
        self.archive = archive
        self.include_asset = include_asset
        self.digest = digest
        self.urls: list[str] = []

    def fetch_release(self) -> dict:
        assets = [
            {
                "name": "checksums.txt",
                "browser_download_url": "https://example.test/checksums.txt",
                "digest": "sha256:"
                + hashlib.sha256(self._checksums().encode()).hexdigest(),
            }
        ]
        if self.include_asset:
            assets.append(
                {
                    "name": ASSET,
                    "browser_download_url": "https://example.test/archive.tar.gz",
                    "digest": self.digest
                    or "sha256:" + hashlib.sha256(self.archive).hexdigest(),
                }
            )
        return {"assets": assets}

    def download(self, url: str) -> bytes:
        self.urls.append(url)
        if url.endswith("checksums.txt"):
            return self._checksums().encode()
        return self.archive

    def _checksums(self) -> str:
        digest = hashlib.sha256(self.archive).hexdigest()
        return f"{digest}  {ASSET}\n"


def _archive(tmp_path: Path) -> bytes:
    binary = tmp_path / "agent-desktop"
    binary.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    helper = tmp_path / "agent-desktop-linux-clipboard-owner"
    helper.write_text("helper\n", encoding="utf-8")
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as bundle:
        bundle.add(binary, arcname="agent-desktop")
        bundle.add(helper, arcname="agent-desktop-linux-clipboard-owner")
    return payload.getvalue()


def _install(tmp_path: Path, fake: FakeRelease, **kwargs):
    return install_release(
        source=fake,
        root=tmp_path / "runtime",
        attest=lambda _path: "checksum-only",
        open_guide=lambda _path: "not_needed",
        **kwargs,
    )


def test_install_checks_the_checksum_and_keeps_the_helper(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(install, "asset_name", lambda version="1.0.2": ASSET)
    fake = FakeRelease(_archive(tmp_path))

    result = _install(tmp_path, fake)

    binary = Path(result["path"])
    assert result["source"] == "managed"
    assert binary.name == "agent-desktop"
    assert (binary.parent / "agent-desktop-linux-clipboard-owner").is_file()
    assert binary.stat().st_mode & stat.S_IXUSR
    assert (binary.parent / "install.json").is_file()
    assert "https://example.test/archive.tar.gz" in fake.urls


def test_checksum_mismatch_installs_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(install, "asset_name", lambda version="1.0.2": ASSET)
    fake = FakeRelease(_archive(tmp_path), digest="sha256:" + "ab" * 32)

    with pytest.raises(DesktopInstallError, match="disagree|mismatch"):
        _install(tmp_path, fake)

    assert not (tmp_path / "runtime").exists()
    assert "https://example.test/archive.tar.gz" not in fake.urls


def test_failed_attestation_installs_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(install, "asset_name", lambda version="1.0.2": ASSET)

    def reject(_path: Path) -> str:
        raise DesktopInstallError("attestation failed")

    with pytest.raises(DesktopInstallError, match="attestation"):
        install_release(
            source=FakeRelease(_archive(tmp_path)),
            root=tmp_path / "runtime",
            attest=reject,
            open_guide=lambda _path: "not_needed",
        )

    assert not (tmp_path / "runtime").exists()


def test_npm_fallback_only_when_the_release_has_no_archive(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(install, "asset_name", lambda version="1.0.2": ASSET)
    placed = tmp_path / "npm-bin" / "agent-desktop"
    placed.parent.mkdir()
    placed.write_text("npm\n", encoding="utf-8")
    calls: list[str] = []

    def npm() -> Path:
        calls.append("npm")
        return placed

    fake = FakeRelease(_archive(tmp_path), include_asset=False)
    result = _install(tmp_path, fake, npm_install=npm)

    assert calls == ["npm"]
    assert result["source"] == "npm"
    assert result["path"] == str(placed)
    assert fake.urls == []


def test_override_and_path_still_resolve(tmp_path: Path, monkeypatch):
    managed = tmp_path / "managed" / "agent-desktop"
    managed.parent.mkdir()
    managed.write_text("managed\n", encoding="utf-8")
    managed.chmod(0o755)
    custom = tmp_path / "custom"
    custom.write_text("custom\n", encoding="utf-8")
    custom.chmod(0o755)
    monkeypatch.setattr(install, "managed_executable", lambda: managed)
    monkeypatch.delenv("SUZENT_AGENT_DESKTOP_BIN", raising=False)
    monkeypatch.setattr(runner.shutil, "which", lambda name: None)

    assert runner.resolve_binary() == str(managed)

    monkeypatch.setattr(runner.shutil, "which", lambda name: "/usr/bin/agent-desktop")
    assert runner.resolve_binary() == str(managed)

    monkeypatch.setenv("SUZENT_AGENT_DESKTOP_BIN", str(custom))
    assert runner.resolve_binary() == str(custom)


def test_install_route_refuses_without_confirmation(monkeypatch):
    def refuse():
        raise AssertionError("downloaded without consent")

    monkeypatch.setattr("suzent.tools.desktop.routes.install_release", refuse)
    client = TestClient(
        Starlette(
            routes=[
                Route(
                    "/desktop/runtime/install",
                    desktop_runtime_install,
                    methods=["POST"],
                )
            ]
        )
    )

    response = client.post("/desktop/runtime/install", json={})

    assert response.status_code == 400
    assert "unsigned" in response.json()["consent"]
    assert "permissions --guide" in CONSENT_TEXT


def test_runtime_status_does_not_download(monkeypatch):
    monkeypatch.delenv("SUZENT_AGENT_DESKTOP_BIN", raising=False)
    monkeypatch.setattr(install, "managed_executable", lambda: None)
    monkeypatch.setattr(install.shutil, "which", lambda _name: None)
    client = TestClient(
        Starlette(routes=[Route("/desktop/runtime", desktop_runtime, methods=["GET"])])
    )

    payload = client.get("/desktop/runtime").json()

    assert payload["installed"] is False
    assert payload["version"] == "1.0.2"
    assert "unsigned" in payload["consent"]


def test_cli_install_asks_before_downloading(monkeypatch):
    from typer.testing import CliRunner

    from suzent.cli.desktop import desktop_app

    calls: list[bool] = []
    monkeypatch.setattr(
        "suzent.tools.desktop.install.runtime_status",
        lambda: {"installed": False, "path": None, "source": None},
    )
    monkeypatch.setattr(
        "suzent.cli.desktop._via_server",
        lambda: None,
    )

    def downloaded():
        calls.append(True)
        return {
            "source": "managed",
            "path": "/opt/agent-desktop",
            "permissionsGuide": "not_needed",
        }

    monkeypatch.setattr("suzent.tools.desktop.install.install_release", downloaded)
    runner_cli = CliRunner()

    declined = runner_cli.invoke(desktop_app, ["install"], input="n\n")
    assert declined.exit_code == 1
    assert calls == []
    assert "unsigned" in declined.output

    accepted = runner_cli.invoke(desktop_app, ["install", "--yes"])
    assert accepted.exit_code == 0
    assert calls == [True]
