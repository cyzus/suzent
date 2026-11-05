"""Relay end-to-end encryption: handshake, vectors, and a phone over a relay."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from suzent.relay import e2e
from suzent.relay.agent import WBIN, RelayState, decode_binary, token_hash
from suzent.relay.e2e import E2E_PATH, E2EError, RelayIdentity
from suzent.relay.service import PHONE_CHANNEL_SECRET, RelayService

from .test_relay_agent import Channel, FakeRelay
from .test_relay_service import MemorySecrets, wait_for

VECTORS = json.loads((Path(__file__).parent / "e2e_vectors.json").read_text())


def scalar(hex_value: str) -> ec.EllipticCurvePrivateKey:
    return ec.derive_private_key(int(hex_value, 16), ec.SECP256R1())


def test_vectors() -> None:
    v = VECTORS
    static = scalar(v["desktop_static_private"])
    assert e2e.public_bytes(static.public_key()).hex() == v["desktop_static_public"]
    assert (
        e2e.b64url(bytes.fromhex(v["desktop_static_public"]))
        == (v["desktop_static_public_b64url"])
    )
    phone_key, first = e2e.initiate(scalar(v["phone_ephemeral_private"]))
    assert first.hex() == v["handshake_message_1"]
    reply, desktop = e2e.respond(
        static, v["channel_token"], first, scalar(v["desktop_ephemeral_private"])
    )
    assert reply.hex() == v["handshake_message_2"]
    phone = e2e.finish(
        phone_key, bytes.fromhex(v["desktop_static_public"]), v["channel_token"], reply
    )
    for message in v["messages"]:
        sender, receiver = (
            (phone, desktop)
            if message["direction"] == "phone_to_desktop"
            else (desktop, phone)
        )
        plaintext = bytes.fromhex(message["plaintext"])
        assert sender.encrypt(plaintext).hex() == message["ciphertext"]
        assert receiver.decrypt(bytes.fromhex(message["ciphertext"])) == plaintext


def handshake(token: str = "channel-token-aaaaaaaaaaaaaaaa") -> tuple[Any, ...]:
    static = ec.generate_private_key(ec.SECP256R1())
    phone_key, first = e2e.initiate()
    reply, desktop = e2e.respond(static, token, first)
    return static, phone_key, reply, desktop


def test_phone_rejects_a_desktop_without_the_key() -> None:
    _, phone_key, reply, _ = handshake()
    impostor = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(E2EError):
        e2e.finish(
            phone_key,
            e2e.public_bytes(impostor.public_key()),
            "channel-token-aaaaaaaaaaaaaaaa",
            reply,
        )


def test_handshake_is_bound_to_the_channel() -> None:
    static, phone_key, reply, _ = handshake()
    with pytest.raises(E2EError):
        e2e.finish(
            phone_key,
            e2e.public_bytes(static.public_key()),
            "another-channel-bbbbbbbbbbbbbbbb",
            reply,
        )


def test_tampered_reply_fails() -> None:
    static, phone_key, reply, _ = handshake()
    tampered = reply[:-1] + bytes([reply[-1] ^ 1])
    with pytest.raises(E2EError):
        e2e.finish(
            phone_key,
            e2e.public_bytes(static.public_key()),
            "channel-token-aaaaaaaaaaaaaaaa",
            tampered,
        )


def test_bad_points_are_rejected() -> None:
    static = ec.generate_private_key(ec.SECP256R1())
    for bad in (b"", b"\x04" + b"\x00" * 64, b"\x02" + b"\x01" * 64):
        with pytest.raises(E2EError):
            e2e.respond(static, "channel-token-aaaaaaaaaaaaaaaa", bad)


def test_replay_and_reorder_fail() -> None:
    static, phone_key, reply, desktop = handshake()
    phone = e2e.finish(
        phone_key,
        e2e.public_bytes(static.public_key()),
        "channel-token-aaaaaaaaaaaaaaaa",
        reply,
    )
    first, second = phone.encrypt(b"one"), phone.encrypt(b"two")
    with pytest.raises(E2EError):
        desktop.decrypt(second)
    assert desktop.decrypt(first) == b"one"
    with pytest.raises(E2EError):
        desktop.decrypt(first)
    assert desktop.decrypt(second) == b"two"


def test_identity_persists_privately(tmp_path: Path) -> None:
    path = tmp_path / "config" / "relay_identity.pem"
    first = RelayIdentity(path)
    assert path.stat().st_mode & 0o777 == 0o600
    assert RelayIdentity(path).public == first.public
    assert len(first.public) == 65


async def caps(request: Request) -> JSONResponse:
    return JSONResponse(
        {"client": request.client.host if request.client else None, "via": "e2e"}
    )


desktop_app = Starlette(
    routes=[
        Route("/mobile/capabilities", caps),
        Route("/hooks/x", caps),
        Route("/secret", caps),
    ]
)


class Phone:
    """A phone talking to the desktop through the phone channel's agent socket."""

    def __init__(self, channel: Channel, descriptor: dict[str, Any]) -> None:
        self.channel = channel
        self.descriptor = descriptor
        self.session: e2e.Session | None = None
        self.socket_id = "phone-1"

    async def next_payload(self) -> bytes:
        while True:
            frame = await self.channel.next()
            if frame.get("id") != self.socket_id:
                continue
            if frame.get("kind") == WBIN:
                return bytes(frame["data"])
            if frame.get("t") in ("wclose", "werr"):
                raise ConnectionError(frame)

    async def connect(self) -> None:
        await self.channel.send({"t": "wopen", "id": self.socket_id, "path": E2E_PATH})
        assert await self.channel.next() == {"t": "wopened", "id": self.socket_id}
        key, first = e2e.initiate()
        await self.channel.send_binary(WBIN, self.socket_id, first)
        reply = await self.next_payload()
        static = base64.urlsafe_b64decode(self.descriptor["key"] + "==")
        self.session = e2e.finish(key, static, self.descriptor["channel"], reply)

    async def request(self, path: str) -> tuple[dict[str, Any], bytes]:
        assert self.session is not None
        frame = {"t": "hreq", "id": path, "method": "GET", "path": path, "headers": {}}
        payload = self.session.encrypt(b"\x00" + json.dumps(frame).encode())
        await self.channel.send_binary(WBIN, self.socket_id, payload)
        head: dict[str, Any] = {}
        body = b""
        while True:
            plaintext = self.session.decrypt(await self.next_payload())
            if plaintext[0] == 0:
                reply = json.loads(plaintext[1:])
                if reply["t"] == "hres":
                    head = reply
                elif reply["t"] == "hend":
                    return head, body
            else:
                _, _, data = decode_binary(plaintext[1:])
                body += data


async def test_phone_over_relay_reaches_only_the_mobile_gateway(
    tmp_path: Path,
) -> None:
    secrets = MemorySecrets()
    async with FakeRelay() as relay:
        service = RelayService(desktop_app, tmp_path / "relay.json", secrets)  # type: ignore[arg-type]
        await service.configure(url=relay.url, key=None, enabled=True)
        await wait_for(service, RelayState.CONNECTED)
        descriptor = service.phone_descriptor()
        assert descriptor is not None
        assert descriptor["channel"] == secrets.values[PHONE_CHANNEL_SECRET]
        assert descriptor["url"] == relay.url
        assert len(base64.urlsafe_b64decode(descriptor["key"] + "==")) == 65
        channel = Channel(relay, token_hash(descriptor["channel"]))

        # The relay itself can't make plaintext requests on the phone channel.
        await channel.send(
            {
                "t": "hreq",
                "id": "p",
                "method": "GET",
                "path": "/mobile/capabilities",
                "headers": {},
            }
        )
        head, _ = await channel.response("p")
        assert head["status"] == 403
        await channel.send({"t": "wopen", "id": "w", "path": "/ws/node"})
        assert (await channel.next())["t"] == "werr"

        phone = Phone(channel, descriptor)
        await phone.connect()
        head, body = await phone.request("/mobile/capabilities")
        assert head["status"] == 200
        assert json.loads(body) == {"client": "mobile-gateway", "via": "e2e"}
        head, _ = await phone.request("/secret")
        assert head["status"] == 404
        head, _ = await phone.request("/hooks/x")
        assert head["status"] == 404

        # A message the relay forged ends the session.
        await channel.send_binary(WBIN, phone.socket_id, b"\x00" * 40)
        with pytest.raises(ConnectionError):
            await phone.next_payload()
        await service.stop()


async def test_reset_changes_the_phone_channel(tmp_path: Path) -> None:
    secrets = MemorySecrets()
    async with FakeRelay() as relay:
        service = RelayService(desktop_app, tmp_path / "relay.json", secrets)  # type: ignore[arg-type]
        await service.configure(url=relay.url, key=None, enabled=True)
        before = service.phone_descriptor()
        await service.reset_channels()
        after = service.phone_descriptor()
        assert before and after
        assert before["channel"] != after["channel"]
        assert before["key"] == after["key"]
        await service.stop()


class StubRelay:
    def phone_descriptor(self) -> dict[str, Any]:
        return {"version": 1, "url": "https://r.example", "channel": "c" * 43, "key": "k"}


def test_invite_and_session_carry_the_relay(tmp_path: Path) -> None:
    from starlette.testclient import TestClient

    from suzent.auth_boundary import AuthBoundaryMiddleware
    from suzent.mobile.pairing import PairingStore
    from suzent.routes.mobile_routes import mobile_routes

    app = Starlette(routes=mobile_routes)
    app.state.mobile_store = PairingStore(tmp_path / "clients.json")
    app.state.relay = StubRelay()
    app.add_middleware(AuthBoundaryMiddleware)
    with TestClient(app) as client:
        invite = client.post("/mobile/pairing/invite", json={})
        assert invite.status_code == 201
        assert invite.json()["relay"] == StubRelay().phone_descriptor()
    with TestClient(app, client=("192.0.2.1", 3000)) as remote:
        assert remote.get("/mobile/relay").status_code == 401
        assert remote.post("/mobile/relay", json={"enabled": False}).status_code == 401
        assert remote.post("/mobile/relay/reset").status_code == 401


def test_session_includes_relay() -> None:
    from types import SimpleNamespace

    from suzent.mobile.client_api import relay_field

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(relay=StubRelay())))
    assert relay_field(request)["relay"]["url"] == "https://r.example"  # type: ignore[arg-type]
    empty = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    assert relay_field(empty) == {}  # type: ignore[arg-type]
