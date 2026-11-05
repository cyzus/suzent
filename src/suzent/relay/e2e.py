"""End-to-end encryption between a paired phone and this Suzent, over a relay.

The relay forwards a phone's WebSocket to ``/__suzent_e2e__``. The phone knows
this desktop's static P-256 public key from the pairing QR code and runs a
Noise-NK-style handshake against it:

1. phone -> desktop: ``e`` (65-byte uncompressed P-256 point)
2. desktop -> phone: ``e'`` and a 16-byte AES-GCM tag over the transcript,
   proving it holds the static key

Keys are ``HKDF-SHA256(ikm = ECDH(e, S) || ECDH(e, e'), salt = transcript)``,
split into a confirmation key and one AES-256-GCM key per direction. Nonces
are per-direction message counters, so a replayed, dropped or reordered
message fails to decrypt and ends the session.

Each encrypted message carries one relay frame (see ``agent.py``): a leading
``0`` byte and JSON text, or ``1`` and a binary frame. The phone plays the
relay's part, so everything the relay protocol tunnels (HTTP, SSE, streamed
bodies, WebSockets) also works inside the encrypted channel.

docs/08-developing/protocols/relay.md describes the format;
tests/relay/e2e_vectors.json pins it for the mobile apps.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import struct
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from starlette.types import ASGIApp, Receive, Scope, Send

from suzent.logger import get_logger
from suzent.relay.agent import PROTOCOL, _Tunnel

logger = get_logger(__name__)

E2E_PATH = "/__suzent_e2e__"
PROTOCOL_NAME = b"suzent-e2e/1"
POINT_SIZE = 65
TAG_SIZE = 16
HANDSHAKE_TIMEOUT_S = 15.0
FRAME_TEXT, FRAME_BINARY = 0, 1


class E2EError(Exception):
    """A handshake or message that must end the session."""


def public_bytes(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


def load_public(data: bytes) -> ec.EllipticCurvePublicKey:
    if len(data) != POINT_SIZE or data[0] != 0x04:
        raise E2EError("Expected an uncompressed P-256 point")
    try:
        return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), data)
    except ValueError:
        raise E2EError("Not a point on P-256") from None


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def nonce(counter: int) -> bytes:
    return b"\x00\x00\x00\x00" + struct.pack(">Q", counter)


@dataclass(frozen=True)
class HandshakeKeys:
    transcript: bytes
    confirm: bytes
    phone_to_desktop: bytes
    desktop_to_phone: bytes


def derive_keys(
    channel_token: str,
    static_public: bytes,
    phone_ephemeral: bytes,
    desktop_ephemeral: bytes,
    es: bytes,
    ee: bytes,
) -> HandshakeKeys:
    transcript = hashlib.sha256(
        PROTOCOL_NAME
        + hashlib.sha256(channel_token.encode()).digest()
        + static_public
        + phone_ephemeral
        + desktop_ephemeral
    ).digest()
    okm = HKDF(
        algorithm=hashes.SHA256(),
        length=96,
        salt=transcript,
        info=PROTOCOL_NAME + b" keys",
    ).derive(es + ee)
    return HandshakeKeys(transcript, okm[:32], okm[32:64], okm[64:])


class Session:
    """One direction pair of AES-256-GCM keys with message counters."""

    def __init__(self, send_key: bytes, receive_key: bytes) -> None:
        self._send = AESGCM(send_key)
        self._receive = AESGCM(receive_key)
        self._sent = 0
        self._received = 0

    def encrypt(self, plaintext: bytes) -> bytes:
        ciphertext = self._send.encrypt(nonce(self._sent), plaintext, None)
        self._sent += 1
        return ciphertext

    def decrypt(self, ciphertext: bytes) -> bytes:
        try:
            plaintext = self._receive.decrypt(nonce(self._received), ciphertext, None)
        except InvalidTag:
            raise E2EError("Message failed authentication") from None
        self._received += 1
        return plaintext


def respond(
    static_key: ec.EllipticCurvePrivateKey,
    channel_token: str,
    first_message: bytes,
    ephemeral_key: ec.EllipticCurvePrivateKey | None = None,
) -> tuple[bytes, Session]:
    """The desktop's half of the handshake: the reply and the session."""
    phone_ephemeral = load_public(first_message)
    ephemeral = ephemeral_key or ec.generate_private_key(ec.SECP256R1())
    desktop_ephemeral = public_bytes(ephemeral.public_key())
    keys = derive_keys(
        channel_token,
        public_bytes(static_key.public_key()),
        first_message,
        desktop_ephemeral,
        static_key.exchange(ec.ECDH(), phone_ephemeral),
        ephemeral.exchange(ec.ECDH(), phone_ephemeral),
    )
    proof = AESGCM(keys.confirm).encrypt(nonce(0), b"", keys.transcript)
    return desktop_ephemeral + proof, Session(
        keys.desktop_to_phone, keys.phone_to_desktop
    )


def initiate(
    ephemeral_key: ec.EllipticCurvePrivateKey | None = None,
) -> tuple[ec.EllipticCurvePrivateKey, bytes]:
    """The phone's first message. Here for tests and as a reference."""
    ephemeral = ephemeral_key or ec.generate_private_key(ec.SECP256R1())
    return ephemeral, public_bytes(ephemeral.public_key())


def finish(
    ephemeral: ec.EllipticCurvePrivateKey,
    static_public: bytes,
    channel_token: str,
    reply: bytes,
) -> Session:
    """The phone's half: check the desktop's proof and open the session."""
    if len(reply) != POINT_SIZE + TAG_SIZE:
        raise E2EError("Malformed handshake reply")
    desktop_ephemeral = reply[:POINT_SIZE]
    peer = load_public(desktop_ephemeral)
    keys = derive_keys(
        channel_token,
        static_public,
        public_bytes(ephemeral.public_key()),
        desktop_ephemeral,
        ephemeral.exchange(ec.ECDH(), load_public(static_public)),
        ephemeral.exchange(ec.ECDH(), peer),
    )
    try:
        AESGCM(keys.confirm).decrypt(nonce(0), reply[POINT_SIZE:], keys.transcript)
    except InvalidTag:
        raise E2EError("The desktop could not prove its key") from None
    return Session(keys.phone_to_desktop, keys.desktop_to_phone)


class RelayIdentity:
    """The desktop's static key for relay E2E, separate from the TLS CA key."""

    def __init__(self, path: Path) -> None:
        if path.exists():
            key = serialization.load_pem_private_key(path.read_bytes(), password=None)
            if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(
                key.curve, ec.SECP256R1
            ):
                raise ValueError("Unsupported relay identity")
            self.key = key
        else:
            self.key = ec.generate_private_key(ec.SECP256R1())
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            pem = self.key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as output:
                output.write(pem)

    @property
    def public(self) -> bytes:
        return public_bytes(self.key.public_key())


class _EncryptedSocket:
    """An ASGI WebSocket that carries relay frames encrypted by a Session.

    Looks enough like a websockets connection for ``_Tunnel``: ``send`` and
    async iteration over str/bytes messages.
    """

    def __init__(self, receive: Receive, send: Send, session: Session) -> None:
        self._receive = receive
        self._send = send
        self._session = session
        self._lock = asyncio.Lock()
        self.closed = False

    async def send(self, message: str | bytes) -> None:
        if isinstance(message, str):
            plaintext = bytes((FRAME_TEXT,)) + message.encode()
        else:
            plaintext = bytes((FRAME_BINARY,)) + message
        # Counters must reach the wire in the order they were used.
        async with self._lock:
            if self.closed:
                return
            await self._send(
                {"type": "websocket.send", "bytes": self._session.encrypt(plaintext)}
            )

    async def __aiter__(self) -> AsyncIterator[str | bytes]:
        while True:
            message = await self._receive()
            if message["type"] == "websocket.disconnect":
                self.closed = True
                return
            data = message.get("bytes")
            if data is None:
                raise E2EError("Plaintext message on an encrypted channel")
            plaintext = self._session.decrypt(data)
            if not plaintext:
                raise E2EError("Empty frame")
            if plaintext[0] == FRAME_TEXT:
                yield plaintext[1:].decode()
            elif plaintext[0] == FRAME_BINARY:
                yield plaintext[1:]
            else:
                raise E2EError("Unknown frame type")


class E2EEndpoint:
    """The only thing a phone channel serves: the encrypted tunnel.

    Plain HTTP requests can only have come from the relay itself, so they get
    403; so does any WebSocket other than ``E2E_PATH``.
    """

    def __init__(
        self, app: ASGIApp, identity: RelayIdentity, channel_token: str
    ) -> None:
        self.app = app
        self.identity = identity
        self.channel_token = channel_token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            body = b'{"error":"This relay channel is end-to-end encrypted"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        if scope["type"] != "websocket" or scope.get("path") != E2E_PATH:
            await send({"type": "websocket.close", "code": 1008})
            return
        if (await receive())["type"] != "websocket.connect":
            return
        await send({"type": "websocket.accept"})
        channel: _EncryptedSocket | None = None
        try:
            async with asyncio.timeout(HANDSHAKE_TIMEOUT_S):
                first = await receive()
            if first["type"] != "websocket.receive" or not first.get("bytes"):
                raise E2EError("Expected a handshake")
            reply, session = respond(
                self.identity.key, self.channel_token, first["bytes"]
            )
            await send({"type": "websocket.send", "bytes": reply})
            channel = _EncryptedSocket(receive, send, session)
            await _Tunnel(channel, self.app, PROTOCOL).serve()  # type: ignore[arg-type]
        except (E2EError, TimeoutError) as exc:
            logger.info("Relay E2E session ended: {}", exc)
        if channel is None or not channel.closed:
            if channel is not None:
                channel.closed = True
            await send({"type": "websocket.close", "code": 1008})
