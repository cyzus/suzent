import pytest

from suzent.core.providers import openai


@pytest.mark.asyncio
async def test_openai_fetches_live_model_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openai, "resolve_api_key", lambda *_: "test-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    class Response:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def raise_for_status(self) -> None:
            return None

        async def json(self) -> dict:
            return {"data": [{"id": "gpt-6.1-sol"}, {"id": "gpt-6-luna"}]}

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def get(self, url: str, **kwargs):
            assert url == "https://api.openai.com/v1/models"
            assert kwargs["headers"]["Authorization"] == "Bearer test-key"
            return Response()

    monkeypatch.setattr(openai.aiohttp, "ClientSession", Session)
    provider = openai.OpenAIProvider(
        "openai", {"OPENAI_BASE_URL": "https://api.openai.com/v1"}
    )

    models = await provider.list_models()

    assert [model.id for model in models] == [
        "openai/gpt-6.1-sol",
        "openai/gpt-6-luna",
    ]
