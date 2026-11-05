"""Desktop side of the suzent-relay wire protocol.

The relay (github.com/cyzus/suzent-relay, a fork of yetone/alma-relay) is a
server the user deploys. Suzent dials out to it over one WebSocket, and the
relay forwards requests that arrive at ``/c/<token>/...`` down that socket as
frames. This module answers those frames by calling the ASGI app in process,
so tunneled requests never look like they came from loopback.

See docs/08-developing/protocols/relay.md for the frame set.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import random
import re
import secrets
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from starlette.types import ASGIApp, Message, Receive, Scope, Send
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from suzent.logger import get_logger

logger = get_logger(__name__)

PROTOCOL = 2
HCHUNK, HBODY, WBIN, WTEXT = 1, 2, 3, 4
# The relay caps one agent frame at 32 MiB; stay well under it.
MAX_CHUNK = 1024 * 1024
REGISTER_TIMEOUT_S = 10.0
MAX_BACKOFF_S = 60.0
# The client address tunneled requests carry. Never a loopback host, so the
# auth boundary treats them like any other remote caller.
RELAY_CLIENT = ("suzent-relay", 0)
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


def new_channel_token() -> str:
    """A fresh 256-bit channel token, in the relay's token alphabet."""
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def encode_binary(kind: int, frame_id: str, payload: bytes) -> bytes:
    """``[kind u8][idLen u8][id utf8][payload]``"""
    raw_id = frame_id.encode()
    if len(raw_id) > 255:
        raise ValueError("frame id too long")
    return bytes((kind, len(raw_id))) + raw_id + payload


def decode_binary(data: bytes) -> tuple[int, str, bytes] | None:
    if len(data) < 2 or len(data) < 2 + data[1]:
        return None
    end = 2 + data[1]
    return data[0], data[2:end].decode(errors="replace"), data[end:]


def normalize_relay_url(url: str) -> str:
    """The relay's base URL as https://host[/prefix], without a trailing slash.

    Raises ``ValueError`` for anything that isn't an http(s) or ws(s) URL.
    """
    parts = urlsplit(url.strip())
    scheme = {"ws": "http", "wss": "https"}.get(parts.scheme, parts.scheme)
    if scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Relay URL must start with https://")
    # Credentials belong in the registration key, which is kept as a secret;
    # an address with user:password@ would end up in relay.json and the logs.
    if parts.username or parts.password:
        raise ValueError("Relay URL must not contain a user name or password")
    return urlunsplit((scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


class RelayState(StrEnum):
    STOPPED = "stopped"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    # The relay refused us (bad registration key, bad token). Retrying the
    # same credentials cannot help, so the agent stops until reconfigured.
    REJECTED = "rejected"
    # Another desktop registered the same channel. Redialling would just
    # knock it off in turn, so the agent stops.
    REPLACED = "replaced"


@dataclass
class RelayStatus:
    state: RelayState = RelayState.STOPPED
    detail: str | None = None
    protocol: int | None = None


class RelayClosed(Exception):
    """The relay ended the session in a way that rules out redialling."""

    def __init__(self, state: RelayState, detail: str) -> None:
        super().__init__(detail)
        self.state = state
        self.detail = detail


_FATAL_CLOSE_CODES = {
    4000: (RelayState.REPLACED, "Another Suzent connected to this relay channel"),
    4002: (RelayState.REJECTED, "The relay rejected the channel"),
    4003: (RelayState.REJECTED, "The relay rejected the registration key"),
    4401: (RelayState.REJECTED, "The relay rejected the registration key"),
}


class RelayAgent:
    """Keeps one relay channel registered and serves it from an ASGI app.

    ``app`` receives every tunneled request; wrap it in :class:`PathGate` to
    limit what the channel exposes.
    """

    def __init__(
        self,
        relay_url: str,
        token: str,
        app: ASGIApp,
        *,
        key: str | None = None,
        name: str = "Suzent",
        version: str = "",
        label: str = "relay",
    ) -> None:
        if not TOKEN_PATTERN.match(token):
            raise ValueError("Relay channel token has the wrong format")
        self.base_url = normalize_relay_url(relay_url)
        self.token = token
        self.app = app
        self.key = key
        self.name = name
        self.version = version
        self.label = label
        self.status = RelayStatus()
        self._task: asyncio.Task | None = None
        self._registered = False

    @property
    def agent_url(self) -> str:
        ws_base = "ws" + self.base_url.removeprefix("http")
        return f"{ws_base}/agent?th={token_hash(self.token)}"

    def public_url(self, path: str = "/") -> str:
        """The address a phone or webhook caller uses for ``path``."""
        return f"{self.base_url}/c/{self.token}{path}"

    def start(self) -> None:
        if self._task is None or self._task.done():
            self.status = RelayStatus(RelayState.CONNECTING)
            self._task = asyncio.create_task(self.run(), name=f"relay-{self.label}")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.status = RelayStatus()

    async def run(self) -> None:
        """Stay registered, redialling with backoff, until stopped or refused."""
        attempt = 0
        while True:
            self.status = RelayStatus(RelayState.CONNECTING, self.status.detail)
            self._registered = False
            try:
                await self._session()
            except RelayClosed as exc:
                logger.warning("Relay {} stopped: {}", self.label, exc.detail)
                self.status = RelayStatus(exc.state, exc.detail)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.status = RelayStatus(RelayState.CONNECTING, _describe(exc))
                logger.debug("Relay {} connection failed: {}", self.label, exc)
            # A session that registered was healthy: whatever ended it, start
            # the backoff over.
            attempt = 0 if self._registered else attempt + 1
            delay = min(MAX_BACKOFF_S, 2 ** min(attempt, 6))
            await self._pause(delay * random.uniform(0.5, 1.0))

    async def _pause(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    async def _session(self) -> None:
        """One connection; sets ``_registered`` once the relay accepts us."""
        try:
            async with connect(
                self.agent_url,
                max_size=None,
                open_timeout=15,
                ping_interval=20,
                ping_timeout=20,
            ) as ws:
                protocol = await self._register(ws)
                self._registered = True
                self.status = RelayStatus(RelayState.CONNECTED, None, protocol)
                logger.info(
                    "Relay {} connected to {} (protocol {})",
                    self.label,
                    self.base_url,
                    protocol,
                )
                await _Tunnel(ws, self.app, protocol).serve()
        except ConnectionClosed as exc:
            code = exc.rcvd.code if exc.rcvd else None
            if code in _FATAL_CLOSE_CODES:
                raise RelayClosed(*_FATAL_CLOSE_CODES[code]) from None
            if self._registered:
                logger.info("Relay {} disconnected ({})", self.label, code)
            raise

    async def _register(self, ws: ClientConnection) -> int:
        frame: dict[str, Any] = {
            "t": "register",
            "tokenHash": token_hash(self.token),
            "name": self.name,
            "ver": self.version,
            "proto": PROTOCOL,
        }
        if self.key:
            frame["key"] = self.key
        await ws.send(json.dumps(frame))
        async with asyncio.timeout(REGISTER_TIMEOUT_S):
            while True:
                message = await ws.recv()
                if isinstance(message, bytes):
                    continue
                reply = json.loads(message)
                if reply.get("t") == "registered":
                    return 2 if int(reply.get("proto") or 1) >= 2 else 1
                if reply.get("t") == "error":
                    # The close code that follows says how bad it is; recv()
                    # raises it as ConnectionClosed.
                    await ws.recv()
                    raise RelayClosed(
                        RelayState.REJECTED, str(reply.get("message") or "")
                    )


def _describe(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "Timed out reaching the relay"
    if isinstance(exc, OSError):
        return "Could not reach the relay"
    return type(exc).__name__


class _Tunnel:
    """Serves the frames of one registered agent socket."""

    def __init__(self, ws: ClientConnection, app: ASGIApp, protocol: int) -> None:
        self.ws = ws
        self.app = app
        self.protocol = protocol
        self.http: dict[str, _HttpExchange] = {}
        self.sockets: dict[str, _SocketExchange] = {}

    async def serve(self) -> None:
        try:
            async for message in self.ws:
                if isinstance(message, bytes):
                    self._on_binary(message)
                else:
                    try:
                        frame = json.loads(message)
                    except ValueError:
                        continue
                    if isinstance(frame, dict):
                        self._on_frame(frame)
        finally:
            for exchange in [*self.http.values(), *self.sockets.values()]:
                exchange.task.cancel()

    async def send_json(self, frame: dict[str, Any]) -> None:
        try:
            await self.ws.send(json.dumps(frame))
        except ConnectionClosed:
            pass

    async def send_payload(
        self, kind: int, frame_id: str, payload: bytes, text: bool = False
    ) -> None:
        """Body bytes or a WebSocket message, binary in protocol 2."""
        if self.protocol >= 2:
            try:
                await self.ws.send(encode_binary(kind, frame_id, payload))
            except ConnectionClosed:
                pass
            return
        if kind == HCHUNK:
            await self.send_json(
                {"t": "hchunk", "id": frame_id, "b": base64.b64encode(payload).decode()}
            )
        elif text:
            await self.send_json({"t": "wmsg", "id": frame_id, "s": payload.decode()})
        else:
            await self.send_json(
                {"t": "wmsg", "id": frame_id, "b": base64.b64encode(payload).decode()}
            )

    def _on_binary(self, data: bytes) -> None:
        decoded = decode_binary(data)
        if decoded is None:
            return
        kind, frame_id, payload = decoded
        if kind == HBODY and (exchange := self.http.get(frame_id)):
            exchange.feed(payload)
        elif kind in (WBIN, WTEXT) and (sock := self.sockets.get(frame_id)):
            sock.feed(payload, text=kind == WTEXT)

    def _on_frame(self, frame: dict[str, Any]) -> None:
        frame_id = str(frame.get("id", ""))
        match frame.get("t"):
            case "hreq" if frame_id and frame_id not in self.http:
                self.http[frame_id] = _HttpExchange(self, frame_id, frame)
            case "hreqend" if exchange := self.http.get(frame_id):
                exchange.finish_body()
            case "hcancel" if exchange := self.http.pop(frame_id, None):
                exchange.task.cancel()
            case "wopen" if frame_id and frame_id not in self.sockets:
                self.sockets[frame_id] = _SocketExchange(self, frame_id, frame)
            case "wmsg" if sock := self.sockets.get(frame_id):
                if isinstance(frame.get("s"), str):
                    sock.feed(frame["s"].encode(), text=True)
                elif isinstance(frame.get("b"), str):
                    sock.feed(base64.b64decode(frame["b"]), text=False)
            case "wclose" if sock := self.sockets.pop(frame_id, None):
                sock.peer_closed(int(frame.get("code") or 1000))


def _build_scope(kind: str, frame: dict[str, Any]) -> Scope | None:
    target = str(frame.get("path") or "/")
    if not target.startswith("/"):
        return None
    raw_path, _, query = target.partition("?")
    headers: list[tuple[bytes, bytes]] = []
    for name, value in (frame.get("headers") or {}).items():
        for item in value if isinstance(value, list) else [value]:
            headers.append(
                (
                    str(name).lower().encode("latin-1", "replace"),
                    str(item).encode("latin-1", "replace"),
                )
            )
    scope: Scope = {
        "type": kind,
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "scheme": "https" if kind == "http" else "wss",
        "path": unquote(raw_path),
        "raw_path": raw_path.encode("latin-1", "replace"),
        "query_string": query.encode("latin-1", "replace"),
        "root_path": "",
        "headers": headers,
        "client": RELAY_CLIENT,
        "server": None,
    }
    if kind == "http":
        scope["method"] = str(frame.get("method") or "GET").upper()
    return scope


class _HttpExchange:
    def __init__(self, tunnel: _Tunnel, frame_id: str, frame: dict[str, Any]) -> None:
        self.tunnel = tunnel
        self.id = frame_id
        self.inbox: asyncio.Queue[Message] = asyncio.Queue()
        self.started = False
        self.ended = False
        if not frame.get("stream"):
            body = base64.b64decode(frame["b"]) if frame.get("b") else b""
            self.inbox.put_nowait(
                {"type": "http.request", "body": body, "more_body": False}
            )
        self.task = asyncio.create_task(self._run(_build_scope("http", frame)))

    def feed(self, chunk: bytes) -> None:
        self.inbox.put_nowait(
            {"type": "http.request", "body": chunk, "more_body": True, "ack": True}
        )

    def finish_body(self) -> None:
        self.inbox.put_nowait({"type": "http.request", "body": b"", "more_body": False})

    async def _run(self, scope: Scope | None) -> None:
        try:
            if scope is None:
                await self._send({"type": "http.response.start", "status": 400})
                await self._send({"type": "http.response.body", "body": b""})
                return
            await self.tunnel.app(scope, self._receive, self._send)
            if not self.ended:
                await self.tunnel.send_json({"t": "hend", "id": self.id})
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Relayed request failed: {}", type(exc).__name__)
            if not self.ended:
                await self.tunnel.send_json(
                    {"t": "herr", "id": self.id, "message": "Internal error"}
                )
        finally:
            self.tunnel.http.pop(self.id, None)

    async def _receive(self) -> Message:
        message = await self.inbox.get()
        if message.pop("ack", False):
            await self.tunnel.send_json(
                {"t": "hack", "id": self.id, "n": len(message["body"])}
            )
        return message

    async def _send(self, message: Message) -> None:
        if self.ended:
            return
        match message["type"]:
            case "http.response.start":
                self.started = True
                headers: dict[str, str | list[str]] = {}
                for raw_name, raw_value in message.get("headers") or []:
                    name = raw_name.decode("latin-1").lower()
                    value = raw_value.decode("latin-1")
                    existing = headers.get(name)
                    if existing is None:
                        headers[name] = value
                    elif isinstance(existing, list):
                        existing.append(value)
                    else:
                        headers[name] = [existing, value]
                await self.tunnel.send_json(
                    {
                        "t": "hres",
                        "id": self.id,
                        "status": int(message["status"]),
                        "headers": headers,
                    }
                )
            case "http.response.body":
                body = bytes(message.get("body") or b"")
                for start in range(0, len(body), MAX_CHUNK):
                    await self.tunnel.send_payload(
                        HCHUNK, self.id, body[start : start + MAX_CHUNK]
                    )
                if not message.get("more_body", False):
                    self.ended = True
                    await self.tunnel.send_json({"t": "hend", "id": self.id})


class _SocketExchange:
    def __init__(self, tunnel: _Tunnel, frame_id: str, frame: dict[str, Any]) -> None:
        self.tunnel = tunnel
        self.id = frame_id
        self.inbox: asyncio.Queue[Message] = asyncio.Queue()
        self.inbox.put_nowait({"type": "websocket.connect"})
        self.accepted = False
        self.closed = False
        self.task = asyncio.create_task(self._run(_build_scope("websocket", frame)))

    def feed(self, payload: bytes, *, text: bool) -> None:
        if text:
            message = {
                "type": "websocket.receive",
                "text": payload.decode(errors="replace"),
            }
        else:
            message = {"type": "websocket.receive", "bytes": payload}
        self.inbox.put_nowait(message)

    def peer_closed(self, code: int) -> None:
        self.closed = True
        self.inbox.put_nowait({"type": "websocket.disconnect", "code": code})

    async def _run(self, scope: Scope | None) -> None:
        try:
            if scope is None:
                await self._send({"type": "websocket.close", "code": 1008})
                return
            await self.tunnel.app(scope, self.inbox.get, self._send)
            if not self.closed:
                await self._send({"type": "websocket.close", "code": 1000})
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Relayed WebSocket failed: {}", type(exc).__name__)
            if not self.closed:
                await self._send({"type": "websocket.close", "code": 1011})
        finally:
            self.tunnel.sockets.pop(self.id, None)

    async def _send(self, message: Message) -> None:
        if self.closed:
            return
        match message["type"]:
            case "websocket.accept":
                self.accepted = True
                await self.tunnel.send_json({"t": "wopened", "id": self.id})
            case "websocket.send" if self.accepted:
                if message.get("text") is not None:
                    await self.tunnel.send_payload(
                        WTEXT, self.id, message["text"].encode(), text=True
                    )
                else:
                    await self.tunnel.send_payload(
                        WBIN, self.id, bytes(message.get("bytes") or b"")
                    )
            case "websocket.close" | "websocket.http.response.start":
                self.closed = True
                if self.accepted:
                    await self.tunnel.send_json(
                        {
                            "t": "wclose",
                            "id": self.id,
                            "code": int(message.get("code") or 1000),
                            "reason": str(message.get("reason") or ""),
                        }
                    )
                else:
                    await self.tunnel.send_json(
                        {"t": "werr", "id": self.id, "message": "Rejected"}
                    )


class PathGate:
    """Lets a relay channel reach only the paths it is meant to expose."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        http_prefixes: tuple[str, ...] = (),
        websocket_paths: tuple[str, ...] = (),
    ) -> None:
        self.app = app
        self.http_prefixes = http_prefixes
        self.websocket_paths = websocket_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] == "http" and path.startswith(self.http_prefixes):
            await self.app(scope, receive, send)
        elif scope["type"] == "websocket" and path in self.websocket_paths:
            await self.app(scope, receive, send)
        elif scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
        else:
            body = b'{"error":"Not available through the relay"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 404,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
