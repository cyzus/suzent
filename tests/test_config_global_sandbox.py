from starlette.testclient import TestClient

from suzent.server import app
from suzent.routes import config_routes


client = TestClient(app)


def test_save_global_sandbox_config_persists_and_updates_runtime(monkeypatch):
    captured: dict = {}

    monkeypatch.setattr(
        config_routes,
        "_load_default_config_file",
        lambda: {"TITLE": "SUZENT", "SANDBOX_VOLUMES": ["C:/old:/mnt/old"]},
    )
    monkeypatch.setattr(
        config_routes,
        "_save_default_config_file",
        lambda cfg: captured.update(cfg),
    )

    response = client.post(
        "/config/sandbox-global",
        json={"sandbox_volumes": ["C:/data:/mnt/data", "C:/data:/mnt/data", " "]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["globalSandboxVolumes"] == ["C:/data:/mnt/data"]
    assert captured["SANDBOX_VOLUMES"] == ["C:/data:/mnt/data"]
    assert config_routes.CONFIG.sandbox_volumes == ["C:/data:/mnt/data"]


def test_save_global_sandbox_config_rejects_invalid_payload():
    response = client.post(
        "/config/sandbox-global",
        json={"sandbox_volumes": "not-a-list"},
    )

    assert response.status_code == 400
    assert "sandbox_volumes" in response.json()["error"]
