from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.routes import node_routes


def _config_response(monkeypatch, *, configured: bool, host: str, port: int) -> dict:
    monkeypatch.setattr(node_routes.CONFIG, "node_lan_bind", configured)
    monkeypatch.setattr(node_routes, "_pairing_addresses", lambda _port: [])
    app = Starlette(routes=[Route("/nodes/config", node_routes.get_node_config)])
    app.state.server_host = host
    app.state.server_port = port

    with TestClient(app) as client:
        response = client.get("/nodes/config")

    assert response.status_code == 200
    return response.json()


def test_node_config_reports_active_external_binding(monkeypatch) -> None:
    data = _config_response(monkeypatch, configured=True, host="0.0.0.0", port=25314)

    assert data["binding_active"] is True


def test_node_config_detects_restart_needed(monkeypatch) -> None:
    data = _config_response(monkeypatch, configured=True, host="127.0.0.1", port=5890)

    assert data["binding_active"] is False
