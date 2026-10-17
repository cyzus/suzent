from types import SimpleNamespace

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route

from suzent.core import stream_registry
from suzent.core.stream_registry import ModelWait, StreamControl
from suzent.routes import chat_routes


@pytest.mark.parametrize("run_name", ["run-current", "client-token"])
async def test_extension_is_scoped_to_run_and_wait(
    monkeypatch: pytest.MonkeyPatch,
    run_name: str,
) -> None:
    control = StreamControl()
    control.run_id = "run-current"
    control.model_wait = ModelWait(300, 1200)
    monkeypatch.setitem(stream_registry.stream_controls, "chat", control)
    queue = SimpleNamespace(
        replay=SimpleNamespace(run_id="run-current", client_token="client-token")
    )
    monkeypatch.setattr(chat_routes, "get_background_queue", lambda _: queue)
    app = Starlette(
        routes=[Route("/extend", chat_routes.extend_model_wait, methods=["POST"])]
    )
    body = {
        "chat_id": "chat",
        "run_id": run_name,
        "wait_id": control.model_wait.wait_id,
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for changes in [{"run_id": "old-run"}, {"wait_id": "old-wait"}]:
            assert (
                await client.post("/extend", json={**body, **changes})
            ).status_code == 409
            assert not control.model_wait.extended.is_set()
        response = await client.post("/extend", json=body)
        assert response.status_code == 200
        assert response.json()["timeout_seconds"] == 1200
        assert control.model_wait.extended.is_set()
        assert (await client.post("/extend", json=body)).status_code == 409
        assert (
            await client.post("/extend", json={**body, "run_id": 42})
        ).status_code == 400
        assert (
            await client.post("/extend", json={"chat_id": "chat"})
        ).status_code == 400
        assert (await client.post("/extend", content="{")).status_code == 400


@pytest.mark.parametrize(
    "state", ["cancelled", "finished", "replaced-control", "no-extension"]
)
async def test_extension_refuses_inactive_waits(
    monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    control = StreamControl()
    control.run_id = "run"
    control.model_wait = ModelWait(300, 1200)
    wait_id = control.model_wait.wait_id
    if state == "cancelled":
        control.cancel_event.set()
    elif state == "finished":
        control.model_wait = None
    elif state == "replaced-control":
        control.run_id = "other"
    else:
        control.model_wait = ModelWait(1200, 1200, wait_id=wait_id)
    monkeypatch.setitem(stream_registry.stream_controls, "chat", control)
    monkeypatch.setattr(chat_routes, "get_background_queue", lambda _: None)
    app = Starlette(
        routes=[Route("/extend", chat_routes.extend_model_wait, methods=["POST"])]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/extend", json={"chat_id": "chat", "run_id": "run", "wait_id": wait_id}
        )
        assert response.status_code == 409
