"""Adding and removing user-defined providers from Settings."""

import json

import pytest
from starlette.testclient import TestClient

from suzent.core.providers import catalog
from suzent.server import app

client = TestClient(app)


@pytest.fixture
def user_dir(tmp_path, monkeypatch):
    """Isolate both the data-dir file and the legacy install-dir one."""
    data = tmp_path / "data"
    install = tmp_path / "install"
    install.mkdir()
    (install / "providers.json").write_text(
        (catalog._CONFIG_DIR / "providers.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        catalog, "user_providers_path", lambda: data / "providers.user.json"
    )
    monkeypatch.setattr(catalog, "_CONFIG_DIR", install)
    catalog.reload_registry()
    yield data, install
    monkeypatch.undo()
    catalog.reload_registry()


def _payload(**overrides):
    payload = {
        "id": "my_relay",
        "label": "My Relay",
        "api_type": "openai",
        "base_url": "https://relay.example.test/v1",
        "env_keys": ["CUSTOM_MY_RELAY_API_KEY"],
        "fields": [
            {
                "key": "CUSTOM_MY_RELAY_API_KEY",
                "label": "API Key",
                "placeholder": "sk-...",
                "type": "secret",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_saves_to_the_data_dir_and_registers(user_dir):
    data, install = user_dir

    resp = client.post("/config/providers/custom", json=_payload())

    assert resp.status_code == 200, resp.text
    saved = json.loads((data / "providers.user.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in saved["providers"]] == ["my_relay"]
    assert not (install / "providers.user.json").exists()
    assert catalog.PROVIDER_REGISTRY_BY_ID["my_relay"].user_defined is True


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"id": "openai"}, "already exists"),
        ({"id": "my/relay"}, "lowercase letters"),
        ({"id": "MyRelay"}, "lowercase letters"),
        ({"api_type": "bedrock"}, "api_type"),
        ({"api_type": "google"}, "api_type"),
        ({"base_url": ""}, "base_url"),
        ({"base_url": "relay.example.test"}, "base_url"),
        (
            {
                "fields": [
                    {
                        "key": "OPENAI_API_KEY",
                        "label": "API Key",
                        "placeholder": "",
                        "type": "secret",
                    }
                ]
            },
            "already used by OpenAI",
        ),
    ],
)
def test_rejects_providers_that_cannot_work(user_dir, overrides, message):
    resp = client.post("/config/providers/custom", json=_payload(**overrides))

    assert resp.status_code in (400, 409)
    assert message in resp.json()["error"]


def test_legacy_install_dir_providers_carry_over(user_dir):
    data, install = user_dir
    legacy = _payload(id="old_one", label="Old One", env_keys=[], fields=[])
    (install / "providers.user.json").write_text(
        json.dumps({"providers": [legacy]}), encoding="utf-8"
    )
    catalog.reload_registry()
    assert "old_one" in catalog.PROVIDER_REGISTRY_BY_ID

    resp = client.post("/config/providers/custom", json=_payload())
    assert resp.status_code == 200, resp.text

    saved = json.loads((data / "providers.user.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in saved["providers"]] == ["old_one", "my_relay"]

    resp = client.delete("/config/providers/custom/old_one")
    assert resp.status_code == 200, resp.text
    catalog.reload_registry()
    assert "old_one" not in catalog.PROVIDER_REGISTRY_BY_ID
    assert "my_relay" in catalog.PROVIDER_REGISTRY_BY_ID


def test_deleting_an_unknown_provider_is_a_404(user_dir):
    assert client.delete("/config/providers/custom/nope").status_code == 404
