import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import BaseModel

from suzent.core.providers.catalog import ProviderSpec
from suzent import llm
from suzent.llm import EmbeddingGenerator, LLMClient


def test_llm_client_passes_resolved_provider_key_to_litellm(monkeypatch):
    monkeypatch.setattr(
        llm,
        "resolve_api_key",
        lambda provider: "synced-key" if provider == "gemini" else None,
    )
    fake_litellm = SimpleNamespace(acompletion=AsyncMock())
    fake_litellm.acompletion.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
    )
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    result = asyncio.run(LLMClient(model="gemini/gemini-2.5-flash").complete("hello"))

    assert result == "ok"
    fake_litellm.acompletion.assert_awaited_once()
    assert fake_litellm.acompletion.await_args.kwargs["api_key"] == "synced-key"


def test_embedding_generator_passes_resolved_provider_key_to_litellm(
    monkeypatch,
):
    monkeypatch.setattr(
        llm,
        "resolve_api_key",
        lambda provider: "synced-key" if provider == "gemini" else None,
    )
    fake_litellm = SimpleNamespace(aembedding=AsyncMock())
    fake_litellm.aembedding.return_value = SimpleNamespace(
        data=[{"embedding": [0.1, 0.2]}]
    )
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    result = asyncio.run(
        EmbeddingGenerator(model="gemini/gemini-embedding-001", dimension=2).generate(
            "hello"
        )
    )

    assert result == [0.1, 0.2]
    fake_litellm.aembedding.assert_awaited_once()
    assert fake_litellm.aembedding.await_args.kwargs["api_key"] == "synced-key"


def test_litellm_client_omits_api_key_when_provider_key_is_unset(monkeypatch):
    monkeypatch.setattr(llm, "resolve_api_key", lambda _provider: None)
    fake_litellm = SimpleNamespace(acompletion=AsyncMock())
    fake_litellm.acompletion.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
    )
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    asyncio.run(LLMClient(model="unknown/model").complete("hello"))

    assert "api_key" not in fake_litellm.acompletion.await_args.kwargs


def test_litellm_client_passes_reasoning_effort(monkeypatch) -> None:
    monkeypatch.setattr(llm, "resolve_api_key", lambda _provider: None)
    monkeypatch.setattr(llm, "_model_supports_reasoning", lambda _model: True)
    fake_litellm = SimpleNamespace(acompletion=AsyncMock())
    fake_litellm.acompletion.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
    )
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    result = asyncio.run(
        LLMClient(model="openai/example").complete("hello", reasoning_effort="minimal")
    )

    assert result == "ok"
    assert fake_litellm.acompletion.await_args.kwargs["reasoning_effort"] == "minimal"


def test_litellm_client_omits_reasoning_effort_for_unknown_models(monkeypatch) -> None:
    monkeypatch.setattr(llm, "resolve_api_key", lambda _provider: None)
    fake_litellm = SimpleNamespace(acompletion=AsyncMock())
    fake_litellm.acompletion.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
    )
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    result = asyncio.run(
        LLMClient(model="unknown/model").complete("hello", reasoning_effort="minimal")
    )

    assert result == "ok"
    assert "reasoning_effort" not in fake_litellm.acompletion.await_args.kwargs


def test_litellm_client_routes_openai_compat_provider_to_openai_base(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        llm,
        "resolve_api_key",
        lambda provider: "synced-key" if provider == "xiaomi_mimo" else None,
    )
    monkeypatch.setitem(
        llm.PROVIDER_REGISTRY_BY_ID,
        "xiaomi_mimo",
        ProviderSpec(
            id="xiaomi_mimo",
            label="Xiaomi MiMo",
            api_type="openai",
            env_keys=["XIAOMI_MIMO_API_KEY"],
            base_url="https://api.xiaomimimo.com/v1",
        ),
    )
    fake_litellm = SimpleNamespace(acompletion=AsyncMock())
    fake_litellm.acompletion.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
    )
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    asyncio.run(LLMClient(model="xiaomi_mimo/mimo-v2.5-omni").complete("hello"))

    kwargs = fake_litellm.acompletion.await_args.kwargs
    assert fake_litellm.acompletion.await_args.kwargs["model"] == (
        "openai/mimo-v2.5-omni"
    )
    assert kwargs["api_key"] == "synced-key"
    assert kwargs["api_base"] == "https://api.xiaomimimo.com/v1"


def test_litellm_client_uses_configured_provider_base_url(monkeypatch) -> None:
    monkeypatch.setattr(
        llm,
        "resolve_api_key",
        lambda provider: "synced-key" if provider == "xiaomi_mimo" else None,
    )
    monkeypatch.setitem(
        llm.PROVIDER_REGISTRY_BY_ID,
        "xiaomi_mimo",
        ProviderSpec(
            id="xiaomi_mimo",
            label="Xiaomi MiMo",
            api_type="openai",
            env_keys=["XIAOMI_MIMO_API_KEY"],
            fields=[
                {
                    "key": "XIAOMI_MIMO_BASE_URL",
                    "label": "Base URL",
                    "placeholder": "",
                    "type": "text",
                }
            ],
            base_url="https://api.xiaomimimo.com/v1",
        ),
    )

    class _SecretManager:
        def get(self, key: str) -> str | None:
            if key == "XIAOMI_MIMO_BASE_URL":
                return "https://custom.example.test/v1"
            return None

    monkeypatch.setattr(
        "suzent.core.secrets.get_secret_manager", lambda: _SecretManager()
    )
    fake_litellm = SimpleNamespace(acompletion=AsyncMock())
    fake_litellm.acompletion.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
    )
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    asyncio.run(LLMClient(model="xiaomi_mimo/mimo-v2.5-omni").complete("hello"))

    kwargs = fake_litellm.acompletion.await_args.kwargs
    assert kwargs["model"] == "openai/mimo-v2.5-omni"
    assert kwargs["api_base"] == "https://custom.example.test/v1"


def test_litellm_client_retries_without_response_format(monkeypatch) -> None:
    monkeypatch.setattr(llm, "resolve_api_key", lambda _provider: None)
    fake_litellm = SimpleNamespace(acompletion=AsyncMock())
    fake_litellm.acompletion.side_effect = [
        Exception("OpenAIException - Param Incorrect"),
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
        ),
    ]
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    result = asyncio.run(
        LLMClient(model="openai/example").complete(
            "hello", response_format={"type": "json_object"}
        )
    )

    assert result == '{"ok": true}'
    assert fake_litellm.acompletion.await_count == 2
    first_kwargs = fake_litellm.acompletion.await_args_list[0].kwargs
    second_kwargs = fake_litellm.acompletion.await_args_list[1].kwargs
    assert first_kwargs["response_format"] == {"type": "json_object"}
    assert "response_format" not in second_kwargs


def test_litellm_client_continues_retrying_optional_params(monkeypatch) -> None:
    monkeypatch.setattr(llm, "resolve_api_key", lambda _provider: None)
    fake_litellm = SimpleNamespace(acompletion=AsyncMock())
    fake_litellm.acompletion.side_effect = [
        Exception("OpenAIException - Param Incorrect"),
        Exception("OpenAIException - Param Incorrect"),
        Exception("OpenAIException - Param Incorrect"),
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
        ),
    ]
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    result = asyncio.run(
        LLMClient(model="openai/example").complete(
            "hello",
            temperature=0.3,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
    )

    assert result == '{"ok": true}'
    assert fake_litellm.acompletion.await_count == 4
    assert "response_format" in fake_litellm.acompletion.await_args_list[0].kwargs
    assert "response_format" not in fake_litellm.acompletion.await_args_list[1].kwargs
    assert "max_tokens" not in fake_litellm.acompletion.await_args_list[2].kwargs
    assert "temperature" not in fake_litellm.acompletion.await_args_list[3].kwargs


def test_litellm_client_retries_system_message_as_user_only(monkeypatch) -> None:
    monkeypatch.setattr(llm, "resolve_api_key", lambda _provider: None)
    fake_litellm = SimpleNamespace(acompletion=AsyncMock())
    fake_litellm.acompletion.side_effect = [
        Exception("OpenAIException - Param Incorrect"),
        Exception("OpenAIException - Param Incorrect"),
        Exception("OpenAIException - Param Incorrect"),
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        ),
    ]
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    result = asyncio.run(
        LLMClient(model="xiaomi_mimo/mimo-v2.5-omni").complete(
            "Create a title",
            system="You name chat conversations.",
            temperature=0.3,
            max_tokens=512,
        )
    )

    assert result == "ok"
    retry_messages = fake_litellm.acompletion.await_args_list[3].kwargs["messages"]
    assert retry_messages == [
        {
            "role": "user",
            "content": "You name chat conversations.\n\nCreate a title",
        }
    ]
    assert "max_tokens" not in fake_litellm.acompletion.await_args_list[3].kwargs
    assert "temperature" not in fake_litellm.acompletion.await_args_list[3].kwargs


def test_litellm_client_omits_reasoning_effort_for_unsupported_models(
    monkeypatch,
) -> None:
    monkeypatch.setattr(llm, "resolve_api_key", lambda _provider: None)
    monkeypatch.setattr(llm, "_model_supports_reasoning", lambda _model: False)
    fake_litellm = SimpleNamespace(acompletion=AsyncMock())
    fake_litellm.acompletion.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
    )
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    result = asyncio.run(
        LLMClient(model="xiaomi_mimo/mimo-v2.5-omni").complete(
            "hello", reasoning_effort="none"
        )
    )

    assert result == "ok"
    assert "reasoning_effort" not in fake_litellm.acompletion.await_args.kwargs


def test_litellm_client_retries_without_reasoning_effort(monkeypatch) -> None:
    monkeypatch.setattr(llm, "resolve_api_key", lambda _provider: None)
    monkeypatch.setattr(llm, "_model_supports_reasoning", lambda _model: True)
    fake_litellm = SimpleNamespace(acompletion=AsyncMock())
    fake_litellm.acompletion.side_effect = [
        Exception("OpenAIException - Param Incorrect"),
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        ),
    ]
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    result = asyncio.run(
        LLMClient(model="openai/example").complete("hello", reasoning_effort="none")
    )

    assert result == "ok"
    assert fake_litellm.acompletion.await_count == 2
    first_kwargs = fake_litellm.acompletion.await_args_list[0].kwargs
    second_kwargs = fake_litellm.acompletion.await_args_list[1].kwargs
    assert first_kwargs["reasoning_effort"] == "none"
    assert "reasoning_effort" not in second_kwargs


def test_extract_with_schema_uses_prompt_json_for_unsupported_models(
    monkeypatch,
) -> None:
    class Payload(BaseModel):
        value: str

    monkeypatch.setattr(llm, "resolve_api_key", lambda _provider: None)
    monkeypatch.setattr(llm, "_model_supports_response_schema", lambda _model: False)
    fake_litellm = SimpleNamespace(acompletion=AsyncMock())
    fake_litellm.acompletion.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"value": "ok"}'))]
    )
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    result = asyncio.run(
        LLMClient(model="xiaomi_mimo/mimo-v2.5-omni").extract_with_schema(
            prompt="extract",
            response_model=Payload,
        )
    )

    kwargs = fake_litellm.acompletion.await_args.kwargs
    assert result.value == "ok"
    assert "response_format" not in kwargs
    assert (
        "Return only valid JSON matching this JSON schema"
        in kwargs["messages"][0]["content"]
    )


# --- self-hosted servers keep their chat-template defaults -------------------


def test_a_self_hosted_server_is_told_not_to_think():
    """A utility call is billed a token budget, and a local server keeps
    whatever its chat template defaults to — thinking on, for Qwen3 and
    friends. The reasoning is then charged against max_tokens before a single
    character of the answer exists. Measured on SGLang with a real classifier
    prompt: 1,616 tokens with thinking, 130 without, same verdict."""
    for provider in ("sglang", "vllm"):
        assert llm._chat_template_kwargs(f"{provider}/qwen3-27b") == {
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}
        }, provider


def test_hosted_providers_are_left_alone():
    """The switch is a local-server chat-template kwarg. Sending it to a hosted
    API is at best ignored and at worst a 400."""
    assert llm._chat_template_kwargs("gemini/gemini-2.5-flash") == {}
    assert llm._chat_template_kwargs(None) == {}


def test_the_switch_stays_out_of_non_chat_endpoints(monkeypatch):
    """The model/auth helper also serves /v1/embeddings and
    /v1/images/generations. LiteLLM expands extra_body into whichever body it
    is building, and a strict OpenAI-compatible server rejects an unknown
    field — so a chat-only argument in the shared path would break memory
    indexing to pay for a classifier fix."""
    monkeypatch.setattr(llm, "resolve_api_key", lambda provider: None)

    _model, kwargs = llm._litellm_model_and_kwargs("sglang/qwen3-27b")

    assert "extra_body" not in kwargs


def test_embeddings_do_not_carry_chat_arguments(monkeypatch):
    """The end the previous test guards: an embedding request must not gain a
    chat_template_kwargs field."""
    monkeypatch.setattr(llm, "resolve_api_key", lambda provider: None)
    fake_litellm = SimpleNamespace(aembedding=AsyncMock())
    generator = EmbeddingGenerator(model="sglang/bge-m3")
    fake_litellm.aembedding.return_value = SimpleNamespace(
        data=[{"embedding": [0.1] * generator.dimension}]
    )
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    asyncio.run(generator.generate("hello"))

    assert "extra_body" not in fake_litellm.aembedding.await_args.kwargs


def test_chat_completions_do_carry_it(monkeypatch):
    monkeypatch.setattr(llm, "resolve_api_key", lambda provider: None)
    fake_litellm = SimpleNamespace(acompletion=AsyncMock())
    fake_litellm.acompletion.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
    )
    monkeypatch.setattr(llm, "_litellm", lambda: fake_litellm)

    asyncio.run(LLMClient(model="sglang/qwen3-27b").complete("hello"))

    assert fake_litellm.acompletion.await_args.kwargs["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False}
    }


# --- an empty answer is not a malformed one ----------------------------------


class _Verdict(BaseModel):
    ok: bool


def test_an_empty_completion_is_reported_as_one(monkeypatch):
    """json.loads("") says 'Expecting value: line 1 column 1 (char 0)', which
    reads as malformed output and sends the reader hunting for a formatting
    bug. The model said nothing — usually a reasoning model that spent the
    whole budget before answering — and the error should say so."""
    monkeypatch.setattr(llm, "_model_supports_response_schema", lambda model: False)

    async def empty(self, **kwargs):
        return ""

    monkeypatch.setattr(LLMClient, "complete", empty)

    try:
        asyncio.run(
            LLMClient(model="sglang/qwen3-27b").extract_with_schema(
                prompt="p", response_model=_Verdict
            )
        )
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected the extraction to fail")

    assert "empty completion" in message
    assert "reasoning" in message
    assert "Expecting value" not in message


def test_the_fallback_path_gets_the_same_wrapping(monkeypatch):
    """It used to return straight out of the branch, outside the handler below
    it, so a failure there escaped as whatever the library raised — a bare json
    error, with nothing naming the extraction that failed."""
    monkeypatch.setattr(llm, "_model_supports_response_schema", lambda model: False)

    async def garbage(self, **kwargs):
        return "not json at all"

    monkeypatch.setattr(LLMClient, "complete", garbage)

    try:
        asyncio.run(
            LLMClient(model="sglang/qwen3-27b").extract_with_schema(
                prompt="p", response_model=_Verdict
            )
        )
    except ValueError as exc:
        assert "Failed to extract structured data" in str(exc)
    else:
        raise AssertionError("expected the extraction to fail")


def test_structured_extraction_has_budget_headroom(monkeypatch):
    """The budget is shared with reasoning, and a request that runs out
    mid-thought returns nothing at all rather than something short."""
    monkeypatch.setattr(llm, "_model_supports_response_schema", lambda model: False)
    seen = {}

    async def capture(self, **kwargs):
        seen.update(kwargs)
        return '{"ok": true}'

    monkeypatch.setattr(LLMClient, "complete", capture)

    asyncio.run(
        LLMClient(model="sglang/qwen3-27b").extract_with_schema(
            prompt="p", response_model=_Verdict
        )
    )

    assert seen["max_tokens"] == llm.STRUCTURED_OUTPUT_MAX_TOKENS
    assert llm.STRUCTURED_OUTPUT_MAX_TOKENS >= 4000
