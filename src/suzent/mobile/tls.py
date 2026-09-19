"""Device-local TLS with a QR-distributed, app-scoped trust anchor."""

from __future__ import annotations

import asyncio
import base64
import contextlib
from collections.abc import Iterator
import datetime as dt
import hashlib
import ipaddress
import os
from pathlib import Path
import socket
import ssl
import tempfile
import traceback
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
import uvicorn

from suzent.logger import get_logger

logger = get_logger(__name__)


def private_write(path: Path, value: bytes) -> None:
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class DeviceIdentity:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        identity = directory / "identity.pem"
        if identity.exists():
            pem = identity.read_bytes()
            self.key = serialization.load_pem_private_key(pem, password=None)
            self.ca = x509.load_pem_x509_certificate(pem)
            if not isinstance(self.key, ec.EllipticCurvePrivateKey):
                raise ValueError("Unsupported mobile TLS identity")
            if self.key.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ) != self.ca.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ):
                raise ValueError("Mobile TLS identity does not match")
        else:
            self.key = ec.generate_private_key(ec.SECP256R1())
            now = dt.datetime.now(dt.UTC)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Suzent device")])
            self.ca = (
                x509.CertificateBuilder()
                .subject_name(name)
                .issuer_name(name)
                .public_key(self.key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - dt.timedelta(minutes=5))
                .not_valid_after(now + dt.timedelta(days=7300))
                .add_extension(
                    x509.BasicConstraints(ca=True, path_length=0), critical=True
                )
                .add_extension(
                    x509.KeyUsage(
                        False, False, False, False, False, True, True, False, False
                    ),
                    critical=True,
                )
                .sign(self.key, hashes.SHA256())
            )
            private_write(
                identity,
                self.key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
                + self.ca.public_bytes(serialization.Encoding.PEM),
            )

    def descriptor(self) -> dict[str, Any]:
        der = self.ca.public_bytes(serialization.Encoding.DER)
        return {
            "version": 1,
            "ca_certificate": base64.b64encode(der).decode(),
            "fingerprint": hashlib.sha256(der).hexdigest(),
        }

    def issue(self, hosts: list[str]) -> tuple[Path, Path]:
        now = dt.datetime.now(dt.UTC)
        key = ec.generate_private_key(ec.SECP256R1())
        names: list[x509.GeneralName] = []
        for host in hosts:
            try:
                names.append(x509.IPAddress(ipaddress.ip_address(host)))
            except ValueError:
                names.append(x509.DNSName(host))
        cert = (
            x509.CertificateBuilder()
            .subject_name(
                x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Suzent mobile")])
            )
            .issuer_name(self.ca.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(now + dt.timedelta(days=30))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None), critical=True
            )
            .add_extension(x509.SubjectAlternativeName(names), critical=False)
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
            )
            .sign(self.key, hashes.SHA256())
        )
        cert_path, key_path = (
            self.directory / "server.pem",
            self.directory / "server-key.pem",
        )
        private_write(
            key_path,
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
        )
        private_write(
            cert_path,
            cert.public_bytes(serialization.Encoding.PEM)
            + self.ca.public_bytes(serialization.Encoding.PEM),
        )
        return cert_path, key_path


def local_hosts() -> list[str]:
    import psutil
    from suzent.nodes.discovery import _local_ip

    hosts = [_local_ip()]
    for addresses in psutil.net_if_addrs().values():
        for address in addresses:
            if (
                address.family == socket.AF_INET
                and not ipaddress.ip_address(address.address).is_loopback
            ):
                hosts.append(address.address)
    name = socket.gethostname().split(".")[0]
    if name and name.isascii() and all(c.isalnum() or c == "-" for c in name):
        hosts.insert(1, f"{name}.local")
    return list(dict.fromkeys(hosts + ["127.0.0.1"]))[:16]


class MobileGateway:
    """Never grant loopback/operator privileges through the network listener."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        allowed = path in {
            "/mobile/capabilities",
            "/mobile/pairing/preview",
            "/mobile/pairing/claim",
            "/mobile/pairing/collect",
            "/ws/node",
        }
        if not allowed and not path.startswith("/mobile/client/"):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await JSONResponse({"error": "Not available on mobile gateway"}, 404)(
                    scope, receive, send
                )
            return
        # The gateway has its own authentication boundary even when accessed locally.
        scope = dict(scope, client=("mobile-gateway", 0))
        await self.app(scope, receive, send)


class GatewayServer(uvicorn.Server):
    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


class MobileTLS:
    def __init__(self, app: ASGIApp, directory: Path) -> None:
        self.app, self.directory = app, directory
        self.lock = asyncio.Lock()
        self.server: GatewayServer | None = None
        self.task: asyncio.Task | None = None
        self.refresh_task: asyncio.Task | None = None
        self.identity: DeviceIdentity | None = None
        self.port = 0
        self.hosts: list[str] = []

    async def start(self) -> dict[str, Any]:
        async with self.lock:
            if self.server is None:
                self.identity = await asyncio.to_thread(DeviceIdentity, self.directory)
                self.hosts = await asyncio.to_thread(local_hosts)
                cert, key = await asyncio.to_thread(self.identity.issue, self.hosts)
                port_file = self.directory / "port"
                port = int(port_file.read_text()) if port_file.exists() else 0
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind(("0.0.0.0", port))
                    self.port = sock.getsockname()[1]
                    config = uvicorn.Config(
                        MobileGateway(self.app),
                        lifespan="off",
                        ws="wsproto",
                        ssl_certfile=str(cert),
                        ssl_keyfile=str(key),
                        ssl_version=ssl.PROTOCOL_TLS_SERVER,
                        proxy_headers=False,
                        log_config=None,
                        access_log=False,
                        timeout_graceful_shutdown=3,
                    )
                    config.load()
                    config.ssl.minimum_version = ssl.TLSVersion.TLSv1_2
                    self.server = GatewayServer(config)
                    self.task = asyncio.create_task(self.server.serve(sockets=[sock]))
                    for _ in range(100):
                        if self.task.done():
                            await self.task
                            raise OSError("Mobile TLS listener did not start")
                        if self.server.started:
                            break
                        await asyncio.sleep(0.01)
                    else:
                        raise OSError("Mobile TLS listener start timed out")
                    private_write(port_file, str(self.port).encode())
                    self.refresh_task = asyncio.create_task(self._refresh())
                except BaseException:
                    if self.task:
                        self.task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await self.task
                    self.server = None
                    sock.close()
                    raise
            assert self.identity is not None
            return {
                "tls": self.identity.descriptor(),
                "origins": [
                    f"https://{host}:{self.port}"
                    for host in self.hosts
                    if host != "127.0.0.1"
                ][:6],
            }

    async def _refresh(self) -> None:
        while True:
            await asyncio.sleep(60)
            try:
                hosts = await asyncio.to_thread(local_hosts)
                # Reissue on address changes, or daily for uninterrupted long-running hosts.
                age = (
                    dt.datetime.now().timestamp()
                    - (self.directory / "server.pem").stat().st_mtime
                )
                if hosts != self.hosts or age > 86400:
                    cert, key = await asyncio.to_thread(self.identity.issue, hosts)
                    self.server.config.ssl.load_cert_chain(cert, key)
                    self.hosts = hosts
            except Exception:
                logger.error(
                    "Could not refresh mobile TLS certificate: {}",
                    traceback.format_exc(),
                )

    async def stop(self) -> None:
        if self.refresh_task:
            self.refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.refresh_task
        if self.server:
            self.server.should_exit = True
        if self.task:
            await self.task
        self.server = None
