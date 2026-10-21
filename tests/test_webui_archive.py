"""The release web UI archive round-trips into the served bundle directory."""

from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_webui.py"
spec = importlib.util.spec_from_file_location("suzent_build_webui", SCRIPT)
assert spec is not None and spec.loader is not None
build_webui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_webui)


@pytest.fixture
def target(tmp_path, monkeypatch):
    target = tmp_path / "src" / "suzent" / "webui"
    monkeypatch.setattr(build_webui, "ROOT", tmp_path)
    monkeypatch.setattr(build_webui, "TARGET", target)
    return target


def test_pack_then_install_replaces_the_bundle(tmp_path, target):
    (target / "assets").mkdir(parents=True)
    (target / "index.html").write_text("<html>new</html>", encoding="utf-8")
    (target / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    archive = tmp_path / "suzent-webui.zip"
    build_webui.pack(archive)

    with zipfile.ZipFile(archive) as bundle:
        assert sorted(bundle.namelist()) == ["assets/app.js", "index.html"]

    (target / "index.html").write_text("<html>old</html>", encoding="utf-8")
    (target / "stale.js").write_text("", encoding="utf-8")
    build_webui.install_archive(archive)

    assert (target / "index.html").read_text(encoding="utf-8") == "<html>new</html>"
    assert (target / "assets" / "app.js").is_file()
    assert not (target / "stale.js").exists()
    assert not target.with_name("webui.staging").exists()
    assert not target.with_name("webui.previous").exists()


def test_install_keeps_previous_bundle_when_archive_is_not_a_bundle(tmp_path, target):
    target.mkdir(parents=True)
    (target / "index.html").write_text("<html>old</html>", encoding="utf-8")
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("readme.txt", "no index")

    with pytest.raises(SystemExit):
        build_webui.install_archive(archive)

    assert (target / "index.html").read_text(encoding="utf-8") == "<html>old</html>"


def test_install_rejects_entries_outside_the_bundle(tmp_path, target):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("index.html", "")
        bundle.writestr("../escape.txt", "")

    with pytest.raises(SystemExit):
        build_webui.install_archive(archive)

    assert not (tmp_path / "src" / "suzent" / "escape.txt").exists()
