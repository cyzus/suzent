from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from suzent.core import model_factory
from suzent.core.providers import openai_compat
from suzent.core.providers.openai_compat import OpenAICompatProvider


class _FakeResponse:
    status = 200

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def json(self) -> dict[str, Any]:
        return {"data": [{"id": "local-model"}]}


class _FakeSession:
    last_headers: dict[str, str] | None = None

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    def get(self, _url: str, *, headers: dict[str, str], timeout: Any) -> _FakeResponse:
        self.last_headers = headers
        return _FakeResponse()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_id", ["vllm", "sglang"])
async def test_keyless_local_provider_discovers_models(
    monkeypatch, provider_id: str
) -> None:
    session = _FakeSession()
    monkeypatch.setattr(openai_compat, "resolve_api_key", lambda *_args: None)
    monkeypatch.setattr(openai_compat.aiohttp, "ClientSession", lambda: session)

    provider = OpenAICompatProvider(provider_id, {}, "http://localhost:8000/v1")
    models = await provider.list_models()

    assert [model.id for model in models] == [f"{provider_id}/local-model"]
    assert session.last_headers == {}


def test_keyless_local_provider_creates_pydantic_model(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_handler(model_name: str, api_key: str, spec: Any) -> object:
        captured.update(model_name=model_name, api_key=api_key, spec=spec)
        return object()

    monkeypatch.setattr(model_factory, "resolve_api_key", lambda _provider: None)
    monkeypatch.setitem(model_factory._API_TYPE_HANDLERS, "openai", fake_handler)

    model_factory.create_pydantic_ai_model("vllm/local-model")

    assert captured["model_name"] == "local-model"
    assert captured["api_key"] == ""
    assert captured["spec"].api_key_optional is True


def test_local_request_merges_and_moves_system_messages_first() -> None:
    request = httpx.Request(
        "POST",
        "http://localhost:8000/v1/chat/completions",
        content=json.dumps(
            {
                "model": "local-model",
                "messages": [
                    {"role": "user", "content": "first"},
                    {"role": "system", "content": "base instructions"},
                    {"role": "assistant", "content": "response"},
                    {"role": "system", "content": "runtime reminder"},
                    {"role": "user", "content": "second"},
                ],
            }
        ).encode(),
    )

    rewritten = model_factory._rewrite_local_openai_request(request)
    messages = json.loads(rewritten.content)["messages"]

    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert messages[0]["content"] == "base instructions\n\nruntime reminder"
    assert [message["content"] for message in messages[1:]] == [
        "first",
        "response",
        "second",
    ]


def test_local_request_without_system_message_is_unchanged() -> None:
    request = httpx.Request(
        "POST",
        "http://localhost:8000/v1/chat/completions",
        content=b'{"messages":[{"role":"user","content":"hello"}]}',
    )

    assert model_factory._rewrite_local_openai_request(request) is request
