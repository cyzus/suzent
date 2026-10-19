import json
from unittest.mock import AsyncMock

import pytest

from suzent.routes import onboarding_routes as routes


def setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "get_model_registry", lambda: None)
    monkeypatch.setattr(routes, "get_enabled_models_from_db", lambda: ["p/chat"])
    monkeypatch.setattr(routes, "get_configured_provider_ids", lambda: {"p"})
    monkeypatch.setattr(routes, "recommend_roles", lambda *_: {"primary": ["p/chat"]})


async def test_recommendations_do_not_invoke_a_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup(monkeypatch)
    request = AsyncMock()
    request.json.return_value = {"model": "p/chat"}
    response = await routes.role_recommendations(request)
    assert response.status_code == 200
    assert json.loads(response.body)["roles"]["primary"] == ["p/chat"]


async def test_invalid_selection_is_rejected() -> None:
    request = AsyncMock()
    request.json.return_value = {"model": []}
    assert (await routes.verify_onboarding_model(request)).status_code == 400


async def test_probe_is_bounded_and_redacts_provider_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup(monkeypatch)
    import pydantic_ai

    import suzent.core.model_factory

    class FakeAgent:
        def __init__(self, model: object, **kwargs: object) -> None:
            assert kwargs == {"retries": 0, "model_settings": {"max_tokens": 32}}

        async def run(self, prompt: str) -> None:
            raise RuntimeError("https://provider/?api_key=secret")

    monkeypatch.setattr(pydantic_ai, "Agent", FakeAgent)
    monkeypatch.setattr(
        suzent.core.model_factory, "create_pydantic_ai_model", lambda _: object()
    )
    request = AsyncMock()
    request.json.return_value = {"model": "p/chat"}
    response = await routes.verify_onboarding_model(request)
    assert response.status_code == 502
    assert b"secret" not in response.body
