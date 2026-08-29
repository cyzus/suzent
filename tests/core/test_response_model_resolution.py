from suzent.core.chat_processor import _resolve_response_model


def test_huggingface_model_id_reuses_local_run_provider_prefix() -> None:
    assert (
        _resolve_response_model(
            "Qwen/Qwen3-8B",
            "vllm/Qwen/Qwen3-8B",
            "openai",
        )
        == "vllm/Qwen/Qwen3-8B"
    )


def test_registered_provider_prefix_is_preserved() -> None:
    assert (
        _resolve_response_model(
            "sglang/Qwen/Qwen3-8B",
            "vllm/Qwen/Qwen3-8B",
            "openai",
        )
        == "sglang/Qwen/Qwen3-8B"
    )


def test_huggingface_model_id_uses_response_provider_after_switch() -> None:
    assert (
        _resolve_response_model(
            "Qwen/Qwen3-8B",
            "vllm/Qwen/Qwen3-8B",
            "anthropic",
        )
        == "anthropic/Qwen/Qwen3-8B"
    )
