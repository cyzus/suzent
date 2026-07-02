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
