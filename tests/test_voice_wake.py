"""Wake word: keyword spelling, model download, and the /ws/wake route."""

import hashlib
import io
import tarfile

import pytest
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.testclient import TestClient

from suzent.routes.voice_routes import wake_websocket_endpoint
from suzent.voice import wake

VOCAB = {"n", "ǐ", "h", "ǎo", "HH", "EY1", "S", "UW1", "UW0", "Z", "EH1", "N", "T"}


def test_keyword_lines_spell_chinese_english_and_suzent():
    pytest.importorskip("pypinyin")
    lines = wake.keyword_lines(
        ["你好  Suzent", "Hey Suzent", "  "], {"HEY": ["HH", "EY1"]}, VOCAB
    )
    assert lines == [
        "n ǐ h ǎo S UW1 Z EH1 N T @你好_Suzent",
        "n ǐ h ǎo S UW0 Z EH1 N T @你好_Suzent",
        "HH EY1 S UW1 Z EH1 N T @Hey_Suzent",
        "HH EY1 S UW0 Z EH1 N T @Hey_Suzent",
    ]


def test_keyword_lines_name_words_without_a_pronunciation():
    with pytest.raises(wake.WakeUnavailable) as excinfo:
        wake.keyword_lines(["Hey Zorblax", "Zorblax"], {"HEY": ["HH", "EY1"]}, VOCAB)
    assert excinfo.value.code == "unknown_words"
    assert str(excinfo.value) == "Zorblax"


def test_threshold_for_maps_the_slider():
    assert wake.threshold_for(0.5) == 0.25
    assert wake.threshold_for(1) < wake.threshold_for(0)
    assert wake.threshold_for(7) == wake.threshold_for(1)


def _fake_model(monkeypatch, tmp_path):
    files = {name: f"{name} data".encode() for name in wake.MODEL_FILES}
    monkeypatch.setattr(
        wake,
        "MODEL_FILES",
        {
            name: (f"orig-{name}", hashlib.sha256(data).hexdigest())
            for name, data in files.items()
        },
    )
    monkeypatch.setattr(wake, "model_dir", lambda: tmp_path / "model")
    return files


def _tarball(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:bz2") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(f"{wake.MODEL_NAME}/orig-{name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def test_install_model_takes_the_pinned_files_from_the_tarball(monkeypatch, tmp_path):
    files = _fake_model(monkeypatch, tmp_path)
    fetched = []

    def fetch(url):
        fetched.append(url)
        return _tarball(files)

    target = wake.install_model(fetch)
    assert fetched == [wake.MODEL_TARBALL]
    assert {p.name: p.read_bytes() for p in target.iterdir()} == files
    # Already there: nothing is downloaded again.
    wake.install_model(fetch)
    assert len(fetched) == 1


def test_install_model_falls_back_to_a_mirror_and_checks_it(monkeypatch, tmp_path):
    files = _fake_model(monkeypatch, tmp_path)
    mirror, other = wake.MODEL_FILE_MIRRORS

    def fetch(url):
        if url == wake.MODEL_TARBALL:
            raise OSError("unreachable")
        if url.startswith(mirror):
            return b"tampered"
        return files[url.rsplit("/orig-", 1)[1]]

    target = wake.install_model(fetch)
    assert (target / "tokens.txt").read_bytes() == files["tokens.txt"]


def test_install_model_fails_when_nothing_matches(monkeypatch, tmp_path):
    _fake_model(monkeypatch, tmp_path)
    with pytest.raises(wake.WakeUnavailable) as excinfo:
        wake.install_model(lambda url: b"tampered")
    assert excinfo.value.code == "download_failed"
    assert not (tmp_path / "model").exists()


class _FakeSpotter:
    def __init__(self, config):
        self.config = config

    def accept(self, pcm):
        return "你好 Suzent" if pcm == b"wake" else None


def _wake_app(factory):
    app = Starlette(routes=[WebSocketRoute("/ws/wake", wake_websocket_endpoint)])
    app.state.wake_spotter_factory = factory
    return app


def test_wake_websocket_reports_the_phrase():
    with TestClient(_wake_app(_FakeSpotter)) as client:
        with client.websocket_connect(
            "/ws/wake", headers={"origin": "tauri://localhost"}
        ) as websocket:
            assert websocket.receive_json() == {"type": "ready", "sample_rate": 16000}
            websocket.send_bytes(b"noise")
            websocket.send_bytes(b"wake")
            assert websocket.receive_json() == {"type": "wake", "phrase": "你好 Suzent"}


def test_wake_websocket_says_why_it_cannot_listen():
    def missing(config):
        raise wake.WakeUnavailable("no_model")

    with TestClient(_wake_app(missing)) as client:
        with client.websocket_connect(
            "/ws/wake", headers={"origin": "tauri://localhost"}
        ) as websocket:
            message = websocket.receive_json()
    assert message["type"] == "error"
    assert message["code"] == "no_model"
