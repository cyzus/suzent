"""Wake-word plugin: keyword spelling, model download, and its endpoints."""

import hashlib
import importlib
import importlib.util
import io
import shutil
import sys
import tarfile
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import suzent.plugins.manager as manager_module
from suzent.plugins.manager import PluginManager
from suzent.routes import plugin_routes

PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "wake-word"
TAURI = {"origin": "tauri://localhost"}


def _import_plugin() -> None:
    name = "suzent_plugin_wake_word"
    if name in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(
        name, PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(PLUGIN_DIR)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


_import_plugin()
spotter = importlib.import_module("suzent_plugin_wake_word.spotter")

VOCAB = {"n", "ǐ", "h", "ǎo", "HH", "EY1", "S", "UW1", "UW0", "Z", "EH1", "N", "T"}


def test_keyword_lines_spell_chinese_english_and_suzent():
    pytest.importorskip("pypinyin")
    lines = spotter.keyword_lines(
        ["你好  Suzent", "Hey Suzent", "  "], {"HEY": ["HH", "EY1"]}, VOCAB
    )
    assert lines == [
        "n ǐ h ǎo S UW1 Z EH1 N T @你好_Suzent",
        "n ǐ h ǎo S UW0 Z EH1 N T @你好_Suzent",
        "HH EY1 S UW1 Z EH1 N T @Hey_Suzent",
        "HH EY1 S UW0 Z EH1 N T @Hey_Suzent",
    ]


def test_keyword_lines_name_words_without_a_pronunciation():
    with pytest.raises(spotter.WakeUnavailable) as excinfo:
        spotter.keyword_lines(["Hey Zorblax", "Zorblax"], {"HEY": ["HH", "EY1"]}, VOCAB)
    assert excinfo.value.code == "unknown_words"
    assert str(excinfo.value) == "Zorblax"


def test_threshold_for_maps_the_slider():
    assert spotter.threshold_for(0.5) == 0.25
    assert spotter.threshold_for(1) < spotter.threshold_for(0)
    assert spotter.threshold_for(7) == spotter.threshold_for(1)


def _fake_model(monkeypatch, tmp_path):
    files = {name: f"{name} data".encode() for name in spotter.MODEL_FILES}
    monkeypatch.setattr(
        spotter,
        "MODEL_FILES",
        {
            name: (f"orig-{name}", hashlib.sha256(data).hexdigest())
            for name, data in files.items()
        },
    )
    monkeypatch.setattr(spotter, "model_dir", lambda: tmp_path / "model")
    return files


def _tarball(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:bz2") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(f"{spotter.MODEL_NAME}/orig-{name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def test_install_model_takes_the_pinned_files_from_the_tarball(monkeypatch, tmp_path):
    files = _fake_model(monkeypatch, tmp_path)
    fetched = []

    def fetch(url):
        fetched.append(url)
        return _tarball(files)

    target = spotter.install_model(fetch)
    assert fetched == [spotter.MODEL_TARBALL]
    assert {p.name: p.read_bytes() for p in target.iterdir()} == files
    # Already there: nothing is downloaded again.
    spotter.install_model(fetch)
    assert len(fetched) == 1


def test_install_model_falls_back_to_a_mirror_and_checks_it(monkeypatch, tmp_path):
    files = _fake_model(monkeypatch, tmp_path)
    mirror, other = spotter.MODEL_FILE_MIRRORS

    def fetch(url):
        if url == spotter.MODEL_TARBALL:
            raise OSError("unreachable")
        if url.startswith(mirror):
            return b"tampered"
        return files[url.rsplit("/orig-", 1)[1]]

    target = spotter.install_model(fetch)
    assert (target / "tokens.txt").read_bytes() == files["tokens.txt"]


def test_install_model_fails_when_nothing_matches(monkeypatch, tmp_path):
    _fake_model(monkeypatch, tmp_path)
    with pytest.raises(spotter.WakeUnavailable) as excinfo:
        spotter.install_model(lambda url: b"tampered")
    assert excinfo.value.code == "download_failed"
    assert not (tmp_path / "model").exists()


class _FakeSpotter:
    def __init__(self, config):
        self.config = config

    def accept(self, pcm):
        return "你好 Suzent" if pcm == b"wake" else None


@pytest.fixture
def plugin_app(tmp_path, monkeypatch):
    """An app serving plugin routes, and a switch for the wake-word plugin."""
    plugins = tmp_path / "plugins"
    shutil.copytree(PLUGIN_DIR, plugins / "wake-word")
    state = tmp_path / "plugins.json"
    monkeypatch.setattr(manager_module, "_refresh_live_registries", lambda: None)
    app = Starlette(
        routes=[
            Route(
                "/plugins/{name}/api/{path:path}",
                plugin_routes.plugin_api,
                methods=["GET", "POST"],
            ),
            WebSocketRoute(
                "/plugins/{name}/ws/{path:path}", plugin_routes.plugin_websocket
            ),
        ]
    )

    def switch(enabled: bool) -> None:
        PluginManager([plugins], state, entry_point_group=None).set_enabled(
            "wake-word", enabled
        )
        manager = PluginManager([plugins], state, entry_point_group=None)
        monkeypatch.setattr(manager_module, "_manager", manager, raising=False)

    return app, switch


def test_register_adds_status_model_and_listen(plugin_app):
    app, switch = plugin_app
    switch(True)
    [record] = manager_module.get_plugin_manager().records()
    assert record.status == "loaded", record.error
    assert {(r.path, r.methods) for r in record.routes} == {
        ("status", ("GET",)),
        ("model", ("POST",)),
    }
    assert [s.path for s in record.websockets] == ["listen"]


def test_listen_reports_the_phrase(plugin_app):
    app, switch = plugin_app
    switch(True)
    app.state.wake_spotter_factory = _FakeSpotter
    with TestClient(app) as client:
        with client.websocket_connect(
            "/plugins/wake-word/ws/listen", headers=TAURI
        ) as websocket:
            assert websocket.receive_json() == {"type": "ready", "sample_rate": 16000}
            websocket.send_bytes(b"noise")
            websocket.send_bytes(b"wake")
            assert websocket.receive_json() == {"type": "wake", "phrase": "你好 Suzent"}


def test_listen_says_why_it_cannot_listen(plugin_app):
    def missing(config):
        raise spotter.WakeUnavailable("no_model")

    app, switch = plugin_app
    switch(True)
    app.state.wake_spotter_factory = missing
    with TestClient(app) as client:
        with client.websocket_connect(
            "/plugins/wake-word/ws/listen", headers=TAURI
        ) as websocket:
            message = websocket.receive_json()
    assert message["type"] == "error"
    assert message["code"] == "no_model"


def test_status_reports_what_is_installed(plugin_app, monkeypatch, tmp_path):
    app, switch = plugin_app
    switch(True)
    monkeypatch.setattr(spotter, "model_dir", lambda: tmp_path / "no-model")
    with TestClient(app) as client:
        response = client.get("/plugins/wake-word/api/status")
    assert response.status_code == 200
    assert response.json()["model"] is False


def test_endpoints_are_gone_while_the_plugin_is_off(plugin_app):
    app, switch = plugin_app
    switch(False)
    app.state.wake_spotter_factory = _FakeSpotter
    with TestClient(app) as client:
        assert client.get("/plugins/wake-word/api/status").status_code == 404
        assert client.post("/plugins/wake-word/api/model").status_code == 404
        with client.websocket_connect(
            "/plugins/wake-word/ws/listen", headers=TAURI
        ) as websocket:
            with pytest.raises(WebSocketDisconnect) as excinfo:
                websocket.receive_json()
    assert excinfo.value.code == plugin_routes.PLUGIN_WEBSOCKET_NOT_FOUND
