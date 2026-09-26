import asyncio
import base64
import hashlib
import ssl
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from suzent.mobile.tls import DeviceIdentity, MobileTLS


def test_identity_persists_and_leaf_renewal_preserves_trust(tmp_path: Path) -> None:
    identity = DeviceIdentity(tmp_path)
    descriptor = identity.descriptor()
    assert (
        hashlib.sha256(base64.b64decode(descriptor["ca_certificate"])).hexdigest()
        == descriptor["fingerprint"]
    )
    first, _ = identity.issue(["127.0.0.1"])
    original = first.read_bytes()
    identity = DeviceIdentity(tmp_path)
    assert identity.descriptor() == descriptor
    renewed, _ = identity.issue(["127.0.0.1", "192.168.1.2"])
    assert renewed.read_bytes() != original
    leaf = x509.load_pem_x509_certificate(renewed.read_bytes())
    leaf.verify_directly_issued_by(identity.ca)
    assert (
        str(
            leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            .value[1]
            .value
        )
        == "192.168.1.2"
    )
    assert (tmp_path / "identity.pem").stat().st_mode & 0o077 == 0


def test_corrupt_identity_is_not_silently_replaced(tmp_path: Path) -> None:
    (tmp_path / "identity.pem").write_text("broken")
    with pytest.raises(ValueError):
        DeviceIdentity(tmp_path)
    assert (tmp_path / "identity.pem").read_text() == "broken"


async def test_tls_gateway_validates_identity_and_limits_routes(tmp_path: Path) -> None:
    async def response(request):
        return JSONResponse({"client": request.client.host})

    app = Starlette(
        routes=[Route("/mobile/capabilities", response), Route("/admin", response)]
    )
    service = MobileTLS(app, tmp_path / "device")
    try:
        results = await asyncio.gather(service.start(), service.start())
        assert results[0] == results[1]
        identity = service.identity
        assert identity is not None
        context = ssl.create_default_context(
            cadata=identity.ca.public_bytes(serialization.Encoding.PEM).decode()
        )
        async with httpx.AsyncClient(verify=context, trust_env=False) as client:
            base = f"https://127.0.0.1:{service.port}"
            result = await client.get(base + "/mobile/capabilities")
            assert result.json() == {"client": "mobile-gateway"}
            assert (await client.get(base + "/admin")).status_code == 404
            assert (
                await client.post(base + "/mobile/pairing/invite")
            ).status_code == 404
        wrong = DeviceIdentity(tmp_path / "wrong")
        wrong_context = ssl.create_default_context(
            cadata=wrong.ca.public_bytes(serialization.Encoding.PEM).decode()
        )
        async with httpx.AsyncClient(verify=wrong_context, trust_env=False) as client:
            with pytest.raises(httpx.ConnectError):
                await client.get(base + "/mobile/capabilities")
        async with httpx.AsyncClient(trust_env=False) as client:
            with pytest.raises(httpx.ConnectError):
                await client.get(base + "/mobile/capabilities")
        port = service.port
    finally:
        await service.stop()
    restarted = MobileTLS(app, tmp_path / "device")
    try:
        assert (await restarted.start())["tls"] == results[0]["tls"]
        assert restarted.port == port
    finally:
        await restarted.stop()


def test_secure_invite_is_operator_only_and_keeps_legacy_bootstrap(
    tmp_path: Path,
) -> None:
    from unittest.mock import AsyncMock
    from starlette.testclient import TestClient
    from suzent.auth_boundary import AuthBoundaryMiddleware
    from suzent.mobile.pairing import PairingStore
    from suzent.routes.mobile_routes import mobile_routes

    app = Starlette(routes=mobile_routes)
    app.add_middleware(AuthBoundaryMiddleware)
    app.state.mobile_store = PairingStore(tmp_path / "clients.json")
    descriptor = DeviceIdentity(tmp_path / "identity").descriptor()
    app.state.mobile_tls = AsyncMock()
    app.state.mobile_tls.start.return_value = {
        "tls": descriptor,
        "origins": ["https://192.168.1.2:25443"],
    }
    with TestClient(app) as client:
        secure = client.post("/mobile/pairing/invite", json={"local_tls": True})
        assert secure.status_code == 201
        assert secure.json()["tls"] == descriptor
        assert "token" not in secure.json()
        legacy = client.post("/mobile/pairing/invite", json={})
        assert legacy.status_code == 201
        assert "tls" not in legacy.json()
    with TestClient(app, client=("192.0.2.2", 1234)) as remote:
        assert (
            remote.post("/mobile/pairing/invite", json={"local_tls": True}).status_code
            == 401
        )
        assert remote.get("/mobile/capabilities").json()["local_tls"] == 1
    assert app.state.mobile_tls.start.await_count == 1
