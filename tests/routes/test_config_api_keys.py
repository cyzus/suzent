"""save_api_keys must not persist masked placeholders echoed back by the UI."""

from starlette.testclient import TestClient

from suzent.server import app
from suzent.routes import config_routes

client = TestClient(app)


class _FakeSM:
    def __init__(self):
        self.set_calls: dict[str, str] = {}
        self.deleted: list[str] = []

    def set(self, key, value):
        self.set_calls[key] = value

    def delete(self, key):
        self.deleted.append(key)


def test_masked_values_are_not_persisted(monkeypatch):
    sm = _FakeSM()
    # save_api_keys imports get_secret_manager at call time — patch the source.
    monkeypatch.setattr("suzent.core.secrets.get_secret_manager", lambda: sm)

    class _FakeDB:
        def save_api_key(self, *a, **k):
            pass

    monkeypatch.setattr(config_routes, "get_database", lambda: _FakeDB())

    resp = client.post(
        "/config/api-keys",
        json={
            "keys": {
                # env-masked form ("...{last4} (env)") — must be ignored
                "OPENAI_API_KEY": "sk-a...bcd1 (env)",
                # backend-masked form ("{first4}...{last4}") — the bug: was persisted
                "GEMINI_API_KEY": "AIza...9kJk",
                # a real, full key — must be saved
                "DEEPSEEK_API_KEY": "sk-realdeepseekkey-1234567890abcdef",
            }
        },
    )
    assert resp.status_code == 200

    # The masked placeholders must NOT have been written to the backend.
    assert "GEMINI_API_KEY" not in sm.set_calls
    assert "OPENAI_API_KEY" not in sm.set_calls
    # The real key IS written.
    assert sm.set_calls.get("DEEPSEEK_API_KEY") == "sk-realdeepseekkey-1234567890abcdef"


def _provider_ids(monkeypatch, china: bool) -> list[str]:
    class _FakeDB:
        def get_api_keys(self):
            return {}

    class _NoSecrets:
        def get(self, key):
            return None

        def get_source(self, key):
            return None

    monkeypatch.setattr(config_routes, "get_database", lambda: _FakeDB())
    monkeypatch.setattr("suzent.core.secrets.get_secret_manager", lambda: _NoSecrets())
    monkeypatch.setattr(config_routes.network_region, "china_mode", lambda: china)
    resp = client.get("/config/api-keys")
    assert resp.status_code == 200
    return [provider["id"] for provider in resp.json()["providers"]]


def test_china_mode_lists_reachable_providers_first(monkeypatch):
    global_order = _provider_ids(monkeypatch, china=False)
    china_order = _provider_ids(monkeypatch, china=True)

    assert sorted(china_order) == sorted(global_order)
    assert china_order[:3] == ["deepseek", "dashscope", "moonshot"]
    assert china_order.index("ollama") < china_order.index("openai")
    # Everyone else keeps the registry order.
    rest = [p for p in china_order if p not in config_routes._CHINA_FIRST]
    assert rest == [p for p in global_order if p not in config_routes._CHINA_FIRST]
