"""RelayService: settings, secrets, the webhook channel and its routes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from suzent.core.secrets import is_private_key
from suzent.relay.agent import RelayState, token_hash
from suzent.relay.service import KEY_SECRET, WEBHOOK_CHANNEL_SECRET, RelayService
from suzent.routes import cron_routes, mobile_routes

from .test_relay_agent import Channel, FakeRelay, backend


class MemorySecrets:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get_backend_only(self, key: str) -> str | None:
        return self.values.get(key)

    def set_backend_only(self, key: str, value: str) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


@pytest.fixture
def secrets() -> MemorySecrets:
    return MemorySecrets()


def make_service(tmp_path: Path, secrets: MemorySecrets) -> RelayService:
    return RelayService(backend, tmp_path / "relay.json", secrets)  # type: ignore[arg-type]


async def wait_for(service: RelayService, state: RelayState) -> None:
    for _ in range(200):
        if service.status()["state"] == state.value:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(service.status())


def test_relay_secrets_stay_out_of_the_environment() -> None:
    assert is_private_key(KEY_SECRET)
    assert is_private_key(WEBHOOK_CHANNEL_SECRET)


async def test_off_by_default(tmp_path: Path, secrets: MemorySecrets) -> None:
    service = make_service(tmp_path, secrets)
    await service.start()
    assert service.status() == {
        "url": None,
        "enabled": False,
        "has_key": False,
        "state": "stopped",
        "detail": None,
        "protocol": None,
    }
    assert service.webhook_url("/hooks/x") is None


async def test_configure_connects_and_persists(
    tmp_path: Path, secrets: MemorySecrets
) -> None:
    async with FakeRelay() as relay:
        service = make_service(tmp_path, secrets)
        await service.configure(url=relay.url + "/", key="k1", enabled=True)
        await wait_for(service, RelayState.CONNECTED)
        assert relay.registrations[0]["key"] == "k1"
        token = secrets.values[WEBHOOK_CHANNEL_SECRET]
        assert service.webhook_url("/hooks/abc") == f"{relay.url}/c/{token}/hooks/abc"
        saved = json.loads((tmp_path / "relay.json").read_text())
        assert saved == {"url": relay.url, "enabled": True}
        assert "k1" not in (tmp_path / "relay.json").read_text()
        assert service.status()["has_key"] is True

        # A second service reads the same settings back and keeps the token.
        await service.stop()
        again = make_service(tmp_path, secrets)
        await again.start()
        await wait_for(again, RelayState.CONNECTED)
        assert again.webhook_url("/hooks/abc") == f"{relay.url}/c/{token}/hooks/abc"
        await again.stop()


async def test_webhook_channel_only_reaches_hooks(
    tmp_path: Path, secrets: MemorySecrets
) -> None:
    async with FakeRelay() as relay:
        service = make_service(tmp_path, secrets)
        await service.configure(url=relay.url, key=None, enabled=True)
        await wait_for(service, RelayState.CONNECTED)
        channel = Channel(relay, token_hash(secrets.values[WEBHOOK_CHANNEL_SECRET]))
        await channel.send(
            {"t": "hreq", "id": "1", "method": "GET", "path": "/secret", "headers": {}}
        )
        head, _ = await channel.response("1")
        assert head["status"] == 404
        await channel.send(
            {
                "t": "hreq",
                "id": "2",
                "method": "GET",
                "path": "/hooks/whoami",
                "headers": {},
            }
        )
        head, _ = await channel.response("2")
        assert head["status"] == 200
        await service.stop()


async def test_key_kept_replaced_and_removed(
    tmp_path: Path, secrets: MemorySecrets
) -> None:
    service = make_service(tmp_path, secrets)
    await service.configure(url="https://relay.example.com", key="k1", enabled=False)
    await service.configure(url="https://relay.example.com", key=None, enabled=False)
    assert secrets.values[KEY_SECRET] == "k1"
    await service.configure(url="https://relay.example.com", key="k2", enabled=False)
    assert secrets.values[KEY_SECRET] == "k2"
    await service.configure(url="https://relay.example.com", key="", enabled=False)
    assert KEY_SECRET not in secrets.values


async def test_rejects_bad_settings(tmp_path: Path, secrets: MemorySecrets) -> None:
    service = make_service(tmp_path, secrets)
    with pytest.raises(ValueError):
        await service.configure(url=None, key=None, enabled=True)
    with pytest.raises(ValueError):
        await service.configure(url="relay.example.com", key=None, enabled=False)


async def test_reset_issues_a_new_channel(
    tmp_path: Path, secrets: MemorySecrets
) -> None:
    async with FakeRelay() as relay:
        service = make_service(tmp_path, secrets)
        await service.configure(url=relay.url, key=None, enabled=True)
        await wait_for(service, RelayState.CONNECTED)
        before = service.webhook_url("/hooks/x")
        relay.registered.clear()
        await service.reset_channels()
        await asyncio.wait_for(relay.registered.wait(), 5)
        assert service.webhook_url("/hooks/x") != before
        assert (
            relay.registrations[0]["tokenHash"] != relay.registrations[-1]["tokenHash"]
        )
        await service.stop()


def _request(app: object, body: dict | None = None) -> Request:
    raw = json.dumps(body).encode() if body is not None else b""

    async def receive() -> dict:
        return {"type": "http.request", "body": raw, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/mobile/relay",
            "headers": [],
            "app": app,
        },
        receive,
    )


async def test_routes(tmp_path: Path, secrets: MemorySecrets) -> None:
    service = make_service(tmp_path, secrets)
    app = SimpleNamespace(state=SimpleNamespace(relay=service))

    response = await mobile_routes.relay_status(_request(app))
    assert json.loads(response.body)["state"] == "stopped"

    response = await mobile_routes.relay_configure(
        _request(app, {"url": "ftp://nope", "enabled": True})
    )
    assert response.status_code == 400

    response = await mobile_routes.relay_configure(
        _request(
            app, {"url": " https://relay.example.com/ ", "key": " k ", "enabled": False}
        )
    )
    assert response.status_code == 200
    data = json.loads(response.body)
    assert data["url"] == "https://relay.example.com"
    assert data["has_key"] is True
    assert "key" not in data
    assert secrets.values[KEY_SECRET] == "k"

    response = await mobile_routes.relay_reset(_request(app, {}))
    assert response.status_code == 200


async def test_webhook_urls_include_relay(
    tmp_path: Path, secrets: MemorySecrets
) -> None:
    async with FakeRelay() as relay:
        service = make_service(tmp_path, secrets)
        await service.configure(url=relay.url, key=None, enabled=True)
        request = _request(SimpleNamespace(state=SimpleNamespace(relay=service)))
        urls = cron_routes._webhook_urls(request, "/hooks/tok")
        token = secrets.values[WEBHOOK_CHANNEL_SECRET]
        assert urls == {
            "webhook_path": "/hooks/tok",
            "webhook_relay_url": f"{relay.url}/c/{token}/hooks/tok",
        }
        await service.stop()
    assert cron_routes._webhook_urls(_request(None), "/hooks/tok") == {
        "webhook_path": "/hooks/tok"
    }
