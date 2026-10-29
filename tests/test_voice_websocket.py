import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from suzent.routes.voice_routes import voice_websocket_endpoint
from suzent.voice.realtime import VoiceBridge


class FakeSession:
    audio_input_sample_rate = 16000
    audio_output_sample_rate = 24000

    def __init__(self):
        self.audio = []
        self.interrupts = []

    async def send_audio(self, data):
        self.audio.append(data)

    async def stream_audio(self):
        yield b"speaker"
        while True:
            await __import__("asyncio").sleep(1)

    async def stream_transcripts(self, delta=True):
        assert delta
        yield SimpleNamespace(
            index=1, speaker="user", transcript="hello", delta="hello"
        )
        while True:
            await __import__("asyncio").sleep(1)

    def __aiter__(self):
        return self

    async def __anext__(self):
        await __import__("asyncio").sleep(1)
        return None

    async def interrupt(self, played_ms=0):
        self.interrupts.append(played_ms)

    async def close(self):
        return None

    async def send(self, content, respond=None):
        self.sent = getattr(self, "sent", [])
        self.sent.append((content, respond))

    def enqueue(self, *content, priority="asap"):
        self.queued = getattr(self, "queued", [])
        self.queued.append((content, priority))
        return "q"


class FakeDatabase:
    def __init__(self):
        self.chats = {}
        self.projects = {"proj-1"}

    def get_project(self, project_id):
        return project_id if project_id in self.projects else None

    def get_chat(self, chat_id):
        return self.chats.get(chat_id)

    def create_chat(self, *, chat_id, **kwargs):
        self.chats[chat_id] = kwargs


def _app(monkeypatch, session):
    db = FakeDatabase()
    monkeypatch.setattr("suzent.routes.voice_routes.get_database", lambda: db)

    @asynccontextmanager
    async def factory():
        yield session

    def bridge_factory(websocket, chat_id):
        return VoiceBridge(
            websocket,
            chat_id,
            session_factory=factory,
            model_id="test/model",
            startup_messages=[],
            persist=lambda _entries: None,
        )

    app = Starlette(routes=[WebSocketRoute("/ws/voice", voice_websocket_endpoint)])
    app.state.voice_bridge_factory = bridge_factory
    return app


def _drain(websocket, until):
    """Collect frames (dicts for JSON, bytes for audio) until *until* matches."""
    frames = []
    while True:
        message = websocket.receive()
        if message.get("bytes") is not None:
            frames.append(message["bytes"])
        else:
            frames.append(json.loads(message["text"]))
        if until(frames[-1]):
            return frames


def test_voice_websocket_happy_path(monkeypatch):
    session = FakeSession()
    with TestClient(_app(monkeypatch, session)) as client:
        with client.websocket_connect(
            "/ws/voice", headers={"origin": "tauri://localhost"}
        ) as websocket:
            ready = websocket.receive_json()
            assert ready["type"] == "ready"
            assert ready["input_sample_rate"] == 16000
            assert ready["working"] is False
            assert websocket.receive_json() == {"type": "state", "state": "listening"}
            seen = set()

            def got_both(frame):
                if frame == b"speaker":
                    seen.add("audio")
                if isinstance(frame, dict) and frame.get("type") == "transcript":
                    seen.add("transcript")
                return seen == {"audio", "transcript"}

            frames = _drain(websocket, got_both)
            transcript = next(
                f
                for f in frames
                if isinstance(f, dict) and f.get("type") == "transcript"
            )
            assert transcript["text"] == "hello"
            assert transcript["final"] is False
            assert transcript["id"].endswith(":1")
            assert {"type": "state", "state": "user_speaking"} in frames
            websocket.send_bytes(b"mic")
            websocket.send_json({"type": "interrupt", "played_ms": 20})
            websocket.send_json({"type": "stop"})
            _drain(
                websocket, lambda f: isinstance(f, dict) and f.get("type") == "closed"
            )
    assert session.audio == [b"mic"]
    assert session.interrupts == [20]


def test_voice_websocket_rejects_bad_origin(monkeypatch):
    with TestClient(_app(monkeypatch, FakeSession())) as client:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(
                "/ws/voice", headers={"origin": "https://evil.example"}
            ):
                pass
        assert excinfo.value.code == 1008


class _ClosingBridge:
    def __init__(self, websocket, chat_id):
        self.websocket = websocket

    async def run(self):
        await self.websocket.close()


@pytest.mark.parametrize(
    ("query", "expected"),
    [("?project_id=proj-1", "proj-1"), ("?project_id=missing", None), ("", None)],
)
def test_voice_websocket_files_new_chat_in_project(monkeypatch, query, expected):
    db = FakeDatabase()
    monkeypatch.setattr("suzent.routes.voice_routes.get_database", lambda: db)
    app = Starlette(routes=[WebSocketRoute("/ws/voice", voice_websocket_endpoint)])
    app.state.voice_bridge_factory = _ClosingBridge
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                f"/ws/voice{query}", headers={"origin": "tauri://localhost"}
            ) as websocket:
                websocket.receive_json()
    (chat,) = db.chats.values()
    assert chat["project_id"] == expected
