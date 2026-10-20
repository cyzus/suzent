import pytest

from suzent.core.model_registry import ModelCapabilities, ModelRegistry
from suzent.core.role_recommendations import recommend_roles


def registry(**models: ModelCapabilities) -> ModelRegistry:
    result = ModelRegistry.__new__(ModelRegistry)
    result._capabilities = models
    return result


def test_specialists_are_matched_only_by_known_capability() -> None:
    models = {
        "p/chat": ModelCapabilities(max_input_tokens=1000, supports_vision=True),
        "p/image": ModelCapabilities(mode="image_generation"),
        "p/edit": ModelCapabilities(mode="image_edit"),
        "p/voice": ModelCapabilities(mode="tts"),
        "p/video": ModelCapabilities(mode="video_generation"),
        "p/embed": ModelCapabilities(mode="embedding", output_vector_size=1024),
        "p/unknown": ModelCapabilities(),
    }
    roles = recommend_roles(registry(**models), list(models), {"p"}, "p/chat")
    assert roles["vision"] == ["p/chat"]
    for role, suffix in {
        "image_generation": "image",
        "image_edit": "edit",
        "tts": "voice",
        "video_generation": "video",
        "embedding": "embed",
    }.items():
        assert roles[role] == [f"p/{suffix}"]
    assert all("p/unknown" not in values for values in roles.values())


def test_unknown_and_unenabled_models_are_not_specialist_recommendations() -> None:
    reg = registry(
        **{
            "p/chat": ModelCapabilities(max_input_tokens=1000, supports_vision=True),
            "p/unselected": ModelCapabilities(mode="tts"),
            "q/voice": ModelCapabilities(mode="tts"),
        }
    )
    roles = recommend_roles(
        reg, ["p/chat", "p/image-edit-by-name", "q/voice"], {"p"}, "p/chat"
    )
    assert roles["image_edit"] == []
    assert roles["image_generation"] == []
    assert roles["tts"] == []


def test_unknown_prices_do_not_beat_known_prices() -> None:
    models = {
        "p/main": ModelCapabilities(max_input_tokens=1000, input_cost_per_token=0.02),
        "p/cheap": ModelCapabilities(max_input_tokens=1000, input_cost_per_token=0.001),
        "p/unknown-price": ModelCapabilities(max_input_tokens=1000),
    }
    roles = recommend_roles(registry(**models), list(models), {"p"}, "p/main")
    assert roles["primary"] == ["p/main"]
    assert roles["cheap"] == roles["memory_extraction"] == ["p/cheap"]
    assert roles["dream"] == ["p/main"]


def test_single_unknown_chat_model_can_be_explicit_primary() -> None:
    roles = recommend_roles(registry(), ["custom/model"], {"custom"}, "custom/model")
    assert roles["cheap"] == ["custom/model"]
    assert roles["vision"] == roles["embedding"] == []


@pytest.mark.parametrize(
    "enabled,configured,primary",
    [
        ([], {"p"}, "p/chat"),
        (["p/chat"], set(), "p/chat"),
        (["p/image"], {"p"}, "p/image"),
    ],
)
def test_rejects_unavailable_or_nonchat_primary(
    enabled: list[str], configured: set[str], primary: str
) -> None:
    with pytest.raises(ValueError):
        recommend_roles(
            registry(**{"p/image": ModelCapabilities(mode="image_generation")}),
            enabled,
            configured,
            primary,
        )
