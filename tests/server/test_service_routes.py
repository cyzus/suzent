from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent import server


class _FakeUvicornServer:
    should_exit = False


def _app() -> Starlette:
    app = Starlette(
        routes=[
            Route("/health", server.health),
            Route("/ready", server.readiness),
            Route("/service/status", server.service_runtime_status),
            Route("/service/stop", server.stop_service, methods=["POST"]),
        ]
    )
    app.state.background_services_ready = False
    app.state.uvicorn_server = _FakeUvicornServer()
    return app


def test_health_identifies_suzent_backend(monkeypatch) -> None:
    monkeypatch.setenv("SUZENT_RUN_MODE", "service")

    response = TestClient(_app()).get("/health")

    assert response.status_code == 200
    assert response.json()["app"] == "suzent"
    assert response.json()["status"] == "ok"
    assert response.json()["run_mode"] == "service"
    assert isinstance(response.json()["pid"], int)


def test_readiness_changes_after_background_startup() -> None:
    app = _app()
    client = TestClient(app)

    starting = client.get("/ready")
    app.state.background_services_ready = True
    ready = client.get("/ready")

    assert starting.status_code == 503
    assert starting.json()["status"] == "starting"
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


def test_runtime_status_contains_only_process_health_fields() -> None:
    app = _app()
    app.state.background_services_ready = True

    response = TestClient(app).get("/service/status")

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["rss_bytes"] > 0
    assert response.json()["threads"] > 0
    assert "control_token" not in response.json()


def test_graceful_stop_requires_private_token(monkeypatch) -> None:
    app = _app()
    monkeypatch.setenv("SUZENT_SERVICE_CONTROL_TOKEN", "private-token")
    client = TestClient(app)

    forbidden = client.post(
        "/service/stop", headers={"X-Suzent-Service-Token": "wrong"}
    )
    accepted = client.post(
        "/service/stop", headers={"X-Suzent-Service-Token": "private-token"}
    )

    assert forbidden.status_code == 403
    assert accepted.status_code == 202
    assert app.state.uvicorn_server.should_exit is True


def test_graceful_stop_is_disabled_without_token(monkeypatch) -> None:
    monkeypatch.delenv("SUZENT_SERVICE_CONTROL_TOKEN", raising=False)

    response = TestClient(_app()).post("/service/stop")

    assert response.status_code == 409
