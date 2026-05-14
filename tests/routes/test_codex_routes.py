from starlette.testclient import TestClient

from suzent.core.codex_session import CodexCommandResult, CodexSessionStatus
from suzent.routes import codex_routes
from suzent.server import app


client = TestClient(app)


def status_payload(state: str = "connected") -> CodexSessionStatus:
    return CodexSessionStatus(
        status=state,
        connected=state == "connected",
        auth_mode="chatgpt" if state == "connected" else None,
        executable="codex",
        codex_home="/tmp/codex",
        message="Codex is logged in using ChatGPT."
        if state == "connected"
        else "Codex is not connected.",
    )


def test_codex_status_route_persists_non_secret_state(monkeypatch, temp_db):
    class FakeService:
        def get_status(self):
            return status_payload()

    monkeypatch.setattr(codex_routes, "get_database", lambda: temp_db)
    monkeypatch.setattr(
        codex_routes, "get_codex_session_service", lambda _home=None: FakeService()
    )

    response = client.get("/codex/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"]["status"] == "connected"
    assert payload["status"]["auth_mode"] == "chatgpt"
    assert payload["config"]["enabled"] is True

    stored = temp_db.get_codex_connector_config()
    assert stored is not None
    assert stored.enabled is True
    assert stored.last_status == "connected"


def test_codex_login_route_starts_login(monkeypatch, temp_db):
    class FakeService:
        def start_login(self, *, device_auth: bool = False):
            assert device_auth is False
            return CodexCommandResult(
                success=True,
                message="Started Codex browser login.",
                status=status_payload("not_logged_in"),
            )

    monkeypatch.setattr(codex_routes, "get_database", lambda: temp_db)
    monkeypatch.setattr(
        codex_routes, "get_codex_session_service", lambda _home=None: FakeService()
    )

    response = client.post("/codex/login", json={})

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_codex_logout_route_clears_enabled_state(monkeypatch, temp_db):
    temp_db.save_codex_connector_config(enabled=True, last_status="connected")

    class FakeService:
        def logout(self):
            return CodexCommandResult(
                success=True,
                message="Codex logout completed.",
                status=status_payload("not_logged_in"),
            )

    monkeypatch.setattr(codex_routes, "get_database", lambda: temp_db)
    monkeypatch.setattr(
        codex_routes, "get_codex_session_service", lambda _home=None: FakeService()
    )

    response = client.post("/codex/logout", json={})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert temp_db.get_codex_connector_config().enabled is False
