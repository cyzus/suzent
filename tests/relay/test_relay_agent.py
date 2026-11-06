"""RelayAgent against an in-process stand-in for suzent-relay."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, StreamingResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket
from websockets.asyncio.server import ServerConnection, serve

from suzent.relay.agent import (
    HBODY,
    HCHUNK,
    WBIN,
    WTEXT,
    PathGate,
    RelayAgent,
    RelayState,
    decode_binary,
    encode_binary,
    new_channel_token,
    normalize_relay_url,
    token_hash,
)


async def whoami(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "client": request.client.host if request.client else None,
            "path": request.url.path,
            "query": request.url.query,
            "agent": request.headers.get("user-agent"),
        }
    )


async def echo(request: Request) -> PlainTextResponse:
    return PlainTextResponse((await request.body()).decode())


async def events(request: Request) -> StreamingResponse:
    async def stream() -> AsyncIterator[bytes]:
        for i in range(3):
            yield f"data: {i}\n\n".encode()

    return StreamingResponse(stream(), media_type="text/event-stream")


async def large(request: Request) -> PlainTextResponse:
    return PlainTextResponse("x" * (2 * 1024 * 1024 + 1))


async def cookies(request: Request) -> PlainTextResponse:
    response = PlainTextResponse("ok")
    response.set_cookie("a", "1")
    response.set_cookie("b", "2")
    return response


async def boom(request: Request) -> PlainTextResponse:
    raise RuntimeError("nope")


async def ws_echo(websocket: WebSocket) -> None:
    await websocket.accept()
    async for text in websocket.iter_text():
        await websocket.send_text(f"echo:{text}")
        await websocket.send_bytes(text.encode()[::-1])


async def ws_reject(websocket: WebSocket) -> None:
    await websocket.close(code=1008)


backend = Starlette(
    routes=[
        Route("/hooks/whoami", whoami),
        Route("/hooks/echo", echo, methods=["POST"]),
        Route("/hooks/events", events),
        Route("/hooks/cookies", cookies),
        Route("/hooks/large", large),
        Route("/hooks/boom", boom),
        Route("/secret", whoami),
        WebSocketRoute("/ws/echo", ws_echo),
        WebSocketRoute("/ws/reject", ws_reject),
    ]
)
gated = PathGate(
    backend, http_prefixes=("/hooks/",), websocket_paths=("/ws/echo", "/ws/reject")
)


class FakeRelay:
    """Speaks the relay side of the agent socket, driven by the test."""

    def __init__(self, *, proto: int = 2, reject: int | None = None) -> None:
        self.proto = proto
        self.reject = reject
        self.registrations: list[dict[str, Any]] = []
        self.agent: ServerConnection | None = None
        self.registered = asyncio.Event()
        self.frames: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.paths: list[str] = []
        # Every registered agent by token hash, for tests with several channels.
        self.agents: dict[str, ServerConnection] = {}
        self.queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}

    async def __aenter__(self) -> FakeRelay:
        self.server = await serve(self.handler, "127.0.0.1", 0, max_size=None)
        port = self.server.sockets[0].getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.server.close()
        await self.server.wait_closed()

    async def handler(self, ws: ServerConnection) -> None:
        self.paths.append(ws.request.path)
        register = json.loads(await ws.recv())
        self.registrations.append(register)
        if self.reject is not None:
            await ws.send(json.dumps({"t": "error", "message": "bad key"}))
            await ws.close(self.reject, "rejected")
            return
        reply: dict[str, Any] = {"t": "registered"}
        if self.proto >= 2:
            reply["proto"] = self.proto
        await ws.send(json.dumps(reply))
        self.agent = ws
        th = register["tokenHash"]
        self.agents[th] = ws
        queue = self.queues.setdefault(th, asyncio.Queue())
        self.registered.set()
        try:
            async for message in ws:
                if isinstance(message, bytes):
                    kind, frame_id, payload = decode_binary(message)
                    frame = {"kind": kind, "id": frame_id, "data": payload}
                else:
                    frame = json.loads(message)
                self.frames.put_nowait(frame)
                queue.put_nowait(frame)
        except Exception:
            pass

    async def send(self, frame: dict[str, Any]) -> None:
        assert self.agent is not None
        await self.agent.send(json.dumps(frame))

    async def send_binary(self, kind: int, frame_id: str, payload: bytes) -> None:
        assert self.agent is not None
        await self.agent.send(encode_binary(kind, frame_id, payload))

    async def next(self) -> dict[str, Any]:
        return await asyncio.wait_for(self.frames.get(), 5)

    async def response(self, frame_id: str) -> tuple[dict[str, Any], bytes]:
        """Collect hres + body until hend (or herr) for one request."""
        head: dict[str, Any] = {}
        body = b""
        while True:
            frame = await self.next()
            if frame.get("id") != frame_id:
                continue
            if frame.get("t") == "hres":
                head = frame
            elif frame.get("kind") == HCHUNK:
                body += frame["data"]
            elif frame.get("t") == "hchunk":
                body += base64.b64decode(frame["b"])
            elif frame.get("t") in ("hend", "herr"):
                head.setdefault("end", frame["t"])
                return head, body


class Channel:
    """One agent socket on FakeRelay, chosen by its token hash."""

    def __init__(self, relay: FakeRelay, th: str) -> None:
        self.ws = relay.agents[th]
        self.queue = relay.queues[th]

    async def send(self, frame: dict[str, Any]) -> None:
        await self.ws.send(json.dumps(frame))

    async def send_binary(self, kind: int, frame_id: str, payload: bytes) -> None:
        await self.ws.send(encode_binary(kind, frame_id, payload))

    async def next(self) -> dict[str, Any]:
        return await asyncio.wait_for(self.queue.get(), 5)

    async def response(self, frame_id: str) -> tuple[dict[str, Any], bytes]:
        head: dict[str, Any] = {}
        body = b""
        while True:
            frame = await self.next()
            if frame.get("id") != frame_id:
                continue
            if frame.get("t") == "hres":
                head = frame
            elif frame.get("kind") == HCHUNK:
                body += frame["data"]
            elif frame.get("t") in ("hend", "herr"):
                head.setdefault("end", frame["t"])
                return head, body


@pytest.fixture
def token() -> str:
    return new_channel_token()


async def connected(relay: FakeRelay, token: str, **kwargs: Any) -> RelayAgent:
    agent = RelayAgent(relay.url, token, gated, version="test", **kwargs)
    agent.start()
    await asyncio.wait_for(relay.registered.wait(), 5)
    for _ in range(100):
        if agent.status.state == RelayState.CONNECTED:
            break
        await asyncio.sleep(0.01)
    return agent


def test_binary_codec_round_trip() -> None:
    frame = encode_binary(WTEXT, "abc", b"hello")
    assert frame[:5] == bytes([WTEXT, 3]) + b"abc"
    assert decode_binary(frame) == (WTEXT, "abc", b"hello")
    assert decode_binary(b"\x01") is None
    assert decode_binary(b"\x01\x05ab") is None


def test_relay_url_normalization() -> None:
    assert (
        normalize_relay_url("https://relay.example.com/") == "https://relay.example.com"
    )
    assert normalize_relay_url("wss://r.example/base/") == "https://r.example/base"
    with pytest.raises(ValueError):
        normalize_relay_url("ftp://relay.example.com")
    with pytest.raises(ValueError):
        normalize_relay_url("relay.example.com")
    with pytest.raises(ValueError):
        normalize_relay_url("https://user:secret@relay.example.com")


def test_token_format_and_urls(token: str) -> None:
    assert len(token) >= 43
    agent = RelayAgent("https://relay.example.com", token, gated)
    assert agent.agent_url == f"wss://relay.example.com/agent?th={token_hash(token)}"
    assert (
        agent.public_url("/hooks/x") == f"https://relay.example.com/c/{token}/hooks/x"
    )
    with pytest.raises(ValueError):
        RelayAgent("https://relay.example.com", "short", gated)


async def test_registers_with_hash_key_and_protocol(token: str) -> None:
    async with FakeRelay() as relay:
        agent = await connected(relay, token, key="reg-key", name="Desk")
        try:
            register = relay.registrations[0]
            assert register["t"] == "register"
            assert register["tokenHash"] == token_hash(token)
            assert register["key"] == "reg-key"
            assert register["name"] == "Desk"
            assert register["proto"] == 2
            assert relay.paths[0] == f"/agent?th={token_hash(token)}"
            assert agent.status.state == RelayState.CONNECTED
            assert agent.status.protocol == 2
        finally:
            await agent.stop()
        assert agent.status.state == RelayState.STOPPED


async def test_http_request_reaches_app_as_remote_client(token: str) -> None:
    async with FakeRelay() as relay:
        agent = await connected(relay, token)
        try:
            await relay.send(
                {
                    "t": "hreq",
                    "id": "1",
                    "method": "GET",
                    "path": "/hooks/whoami?x=1",
                    "headers": {"User-Agent": "GitHub-Hookshot/1"},
                }
            )
            head, body = await relay.response("1")
            assert head["status"] == 200
            assert head["end"] == "hend"
            data = json.loads(body)
            assert data == {
                "client": "suzent-relay",
                "path": "/hooks/whoami",
                "query": "x=1",
                "agent": "GitHub-Hookshot/1",
            }
        finally:
            await agent.stop()


async def test_gate_hides_other_paths(token: str) -> None:
    async with FakeRelay() as relay:
        agent = await connected(relay, token)
        try:
            await relay.send(
                {
                    "t": "hreq",
                    "id": "s",
                    "method": "GET",
                    "path": "/secret",
                    "headers": {},
                }
            )
            head, _ = await relay.response("s")
            assert head["status"] == 404
            await relay.send({"t": "wopen", "id": "w", "path": "/ws/other"})
            frame = await relay.next()
            assert frame == {"t": "werr", "id": "w", "message": "Rejected"}
        finally:
            await agent.stop()


async def test_inline_and_streamed_request_bodies(token: str) -> None:
    async with FakeRelay() as relay:
        agent = await connected(relay, token)
        try:
            await relay.send(
                {
                    "t": "hreq",
                    "id": "a",
                    "method": "POST",
                    "path": "/hooks/echo",
                    "headers": {},
                    "b": base64.b64encode(b"inline").decode(),
                }
            )
            _, body = await relay.response("a")
            assert body == b"inline"

            await relay.send(
                {
                    "t": "hreq",
                    "id": "b",
                    "method": "POST",
                    "path": "/hooks/echo",
                    "headers": {},
                    "stream": True,
                }
            )
            await relay.send_binary(HBODY, "b", b"one,")
            await relay.send_binary(HBODY, "b", b"two")
            await relay.send({"t": "hreqend", "id": "b"})
            acks = 0
            head: dict[str, Any] = {}
            body = b""
            while True:
                frame = await relay.next()
                if frame.get("t") == "hack":
                    acks += frame["n"]
                elif frame.get("t") == "hres":
                    head = frame
                elif frame.get("kind") == HCHUNK:
                    body += frame["data"]
                elif frame.get("t") == "hend":
                    break
            assert head["status"] == 200
            assert body == b"one,two"
            assert acks == len(b"one,two")
        finally:
            await agent.stop()


async def test_large_response_stays_under_phone_message_limit(token: str) -> None:
    """iOS drops WebSocket messages over 1 MiB, so no chunk may come near it."""
    async with FakeRelay() as relay:
        agent = await connected(relay, token)
        try:
            await relay.send(
                {
                    "t": "hreq",
                    "id": "l",
                    "method": "GET",
                    "path": "/hooks/large",
                    "headers": {},
                }
            )
            chunks: list[int] = []
            while True:
                frame = await relay.next()
                if frame.get("kind") == HCHUNK:
                    chunks.append(len(frame["data"]))
                elif frame.get("t") == "hend":
                    break
            assert sum(chunks) == 2 * 1024 * 1024 + 1
            assert len(chunks) > 1
            assert max(chunks) <= 512 * 1024
        finally:
            await agent.stop()


async def test_streaming_response_and_repeated_headers(token: str) -> None:
    async with FakeRelay() as relay:
        agent = await connected(relay, token)
        try:
            await relay.send(
                {
                    "t": "hreq",
                    "id": "e",
                    "method": "GET",
                    "path": "/hooks/events",
                    "headers": {},
                }
            )
            head, body = await relay.response("e")
            assert head["headers"]["content-type"].startswith("text/event-stream")
            assert body == b"data: 0\n\ndata: 1\n\ndata: 2\n\n"

            await relay.send(
                {
                    "t": "hreq",
                    "id": "c",
                    "method": "GET",
                    "path": "/hooks/cookies",
                    "headers": {},
                }
            )
            head, _ = await relay.response("c")
            assert len(head["headers"]["set-cookie"]) == 2
        finally:
            await agent.stop()


async def test_app_error_becomes_500_or_herr(token: str) -> None:
    async with FakeRelay() as relay:
        agent = await connected(relay, token)
        try:
            await relay.send(
                {
                    "t": "hreq",
                    "id": "x",
                    "method": "GET",
                    "path": "/hooks/boom",
                    "headers": {},
                }
            )
            head, _ = await relay.response("x")
            assert head.get("status") == 500 or head["end"] == "herr"
        finally:
            await agent.stop()


async def test_protocol_1_uses_base64_json(token: str) -> None:
    async with FakeRelay(proto=1) as relay:
        agent = await connected(relay, token)
        try:
            assert agent.status.protocol == 1
            await relay.send(
                {
                    "t": "hreq",
                    "id": "1",
                    "method": "GET",
                    "path": "/hooks/whoami",
                    "headers": {},
                }
            )
            frames = []
            while True:
                frame = await relay.next()
                frames.append(frame)
                if frame.get("t") == "hend":
                    break
            assert any(f.get("t") == "hchunk" for f in frames)
            assert not any("kind" in f for f in frames)
        finally:
            await agent.stop()


async def test_websocket_bridge(token: str) -> None:
    async with FakeRelay() as relay:
        agent = await connected(relay, token)
        try:
            await relay.send({"t": "wopen", "id": "w1", "path": "/ws/echo"})
            assert await relay.next() == {"t": "wopened", "id": "w1"}
            await relay.send_binary(WTEXT, "w1", b"hi")
            text = await relay.next()
            assert (text["kind"], text["data"]) == (WTEXT, b"echo:hi")
            binary = await relay.next()
            assert (binary["kind"], binary["data"]) == (WBIN, b"ih")

            await relay.send({"t": "wmsg", "id": "w1", "s": "json"})
            assert (await relay.next())["data"] == b"echo:json"
            await relay.next()

            await relay.send({"t": "wclose", "id": "w1", "code": 1000})
            await asyncio.sleep(0.05)

            await relay.send({"t": "wopen", "id": "w2", "path": "/ws/reject"})
            assert (await relay.next())["t"] == "werr"
        finally:
            await agent.stop()


async def test_hcancel_stops_request(token: str) -> None:
    async with FakeRelay() as relay:
        agent = await connected(relay, token)
        try:
            await relay.send(
                {
                    "t": "hreq",
                    "id": "slow",
                    "method": "POST",
                    "path": "/hooks/echo",
                    "headers": {},
                    "stream": True,
                }
            )
            await relay.send({"t": "hcancel", "id": "slow"})
            await relay.send(
                {
                    "t": "hreq",
                    "id": "next",
                    "method": "GET",
                    "path": "/hooks/whoami",
                    "headers": {},
                }
            )
            head, _ = await relay.response("next")
            assert head["status"] == 200
        finally:
            await agent.stop()


@pytest.mark.parametrize(
    ("code", "state"), [(4003, RelayState.REJECTED), (4401, RelayState.REJECTED)]
)
async def test_rejected_registration_stops(
    token: str, code: int, state: RelayState
) -> None:
    async with FakeRelay(reject=code) as relay:
        agent = RelayAgent(relay.url, token, gated, key="wrong")
        await asyncio.wait_for(agent.run(), 5)
        assert agent.status.state == state
        assert len(relay.registrations) == 1


async def test_replaced_channel_stops_without_redialling(token: str) -> None:
    async with FakeRelay() as relay:
        agent = await connected(relay, token)
        assert relay.agent is not None
        await relay.agent.close(4000, "replaced")
        for _ in range(200):
            if agent.status.state == RelayState.REPLACED:
                break
            await asyncio.sleep(0.01)
        assert agent.status.state == RelayState.REPLACED
        await asyncio.sleep(0.1)
        assert len(relay.registrations) == 1
        await agent.stop()


async def test_redials_after_drop(token: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("suzent.relay.agent.random.uniform", lambda a, b: 0.01)
    async with FakeRelay() as relay:
        agent = await connected(relay, token)
        try:
            assert relay.agent is not None
            relay.registered.clear()
            await relay.agent.close(1012, "restart")
            await asyncio.wait_for(relay.registered.wait(), 5)
            assert len(relay.registrations) == 2
        finally:
            await agent.stop()


async def test_unreachable_relay_keeps_trying(token: str) -> None:
    agent = RelayAgent("http://127.0.0.1:9", token, gated)
    agent.start()
    await asyncio.sleep(0.3)
    assert agent.status.state == RelayState.CONNECTING
    assert agent.status.detail
    await agent.stop()


async def test_backoff_resets_after_a_registered_session(
    token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    delays: list[float] = []
    real_sleep = asyncio.sleep

    async def record(self: RelayAgent, delay: float) -> None:
        delays.append(delay)
        await real_sleep(0)

    monkeypatch.setattr("suzent.relay.agent.random.uniform", lambda a, b: 1.0)
    monkeypatch.setattr(RelayAgent, "_pause", record)
    async with FakeRelay() as relay:
        agent = await connected(relay, token)
        try:
            for _ in range(3):
                assert relay.agent is not None
                relay.registered.clear()
                await relay.agent.close(1012, "restart")
                await asyncio.wait_for(relay.registered.wait(), 5)
            assert delays[:3] == [1, 1, 1]
        finally:
            await agent.stop()
