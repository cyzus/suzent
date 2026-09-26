import json
from types import SimpleNamespace

from suzent.routes import config_routes
from suzent.core.role_router import get_role_router


class FakeDB:
    def __init__(self, api_keys=None):
        self.api_keys = dict(api_keys or {})

    def get_api_keys(self):
        return dict(self.api_keys)

    def save_api_key(self, key, value):
        self.api_keys[key] = value


class FakeRegistry:
    _capabilities = {
        "openai/text-embedding-3-small": SimpleNamespace(mode="embedding"),
        "openai/tts-1": SimpleNamespace(mode="tts"),
    }

    def supports_vision(self, model_id: str) -> bool:
        return model_id.endswith("vision")

    def get_capabilities(self, model_id: str):
        if model_id == "openai/gpt-4.1-vision":
            return SimpleNamespace(mode="chat")
        return self._capabilities.get(model_id)


def _saved_roles(db: FakeDB) -> dict:
    return json.loads(db.api_keys["_ROLE_MODELS_"])


def test_autofill_chat_roles_from_connected_provider(monkeypatch):
    monkeypatch.setattr(
        "suzent.core.model_registry.get_model_registry", lambda: FakeRegistry()
    )
    router = get_role_router()
    router.replace_from_dict({})
    db = FakeDB()

    changed = config_routes._autofill_chat_roles_from_models(
        db, ["openai/gpt-4.1-vision", "openai/gpt-4.1-mini"]
    )

    assert changed is True
    assert _saved_roles(db) == {
        "primary": {"models": ["openai/gpt-4.1-vision", "openai/gpt-4.1-mini"]},
        "cheap": {"models": ["openai/gpt-4.1-vision", "openai/gpt-4.1-mini"]},
        "vision": {"models": ["openai/gpt-4.1-vision"]},
    }


def test_autofill_preserves_existing_roles(monkeypatch):
    monkeypatch.setattr(
        "suzent.core.model_registry.get_model_registry", lambda: FakeRegistry()
    )
    router = get_role_router()
    router.replace_from_dict({})
    db = FakeDB(
        {
            "_ROLE_MODELS_": json.dumps(
                {"primary": {"models": ["anthropic/claude-sonnet"]}}
            )
        }
    )

    changed = config_routes._autofill_chat_roles_from_models(db, ["openai/gpt-4.1"])

    assert changed is True
    assert _saved_roles(db) == {
        "primary": {"models": ["anthropic/claude-sonnet"]},
        "cheap": {"models": ["openai/gpt-4.1"]},
    }


def test_autofill_noops_without_models():
    db = FakeDB()

    assert config_routes._autofill_chat_roles_from_models(db, []) is False
    assert "_ROLE_MODELS_" not in db.api_keys


def test_detects_models_enabled_for_fieldless_provider(monkeypatch):
    monkeypatch.setattr(
        config_routes,
        "PROVIDER_REGISTRY",
        [
            SimpleNamespace(id="openai"),
            SimpleNamespace(id="chatgpt"),
        ],
    )

    models = config_routes._first_newly_enabled_provider_models(
        {"openai": {"enabled_models": ["openai/gpt-4.1"]}},
        {
            "openai": {"enabled_models": ["openai/gpt-4.1"]},
            "chatgpt": {"enabled_models": ["chatgpt/gpt-5"]},
        },
    )

    assert models == ["chatgpt/gpt-5"]


def test_role_suggestions_keep_unregistered_models_available_as_overrides():
    suggestions = config_routes._build_role_suggestions(
        FakeRegistry(),
        ["openai/gpt-4.1-vision", "custom/new-model"],
        {"openai", "custom"},
    )

    for role in (
        "title",
        "memory_extraction",
        "decision",
        "goal_judge",
        "permission_review",
        "dream",
    ):
        assert suggestions[role] == ["openai/gpt-4.1-vision", "custom/new-model"]

    assert suggestions["vision"] == ["openai/gpt-4.1-vision"]
    assert suggestions["embedding"] == ["openai/text-embedding-3-small"]
    assert suggestions["tts"] == ["openai/tts-1"]
    assert suggestions["_unregistered"] == ["custom/new-model"]


def test_image_edit_suggestions_distinguish_unknown_capabilities():
    from suzent.core.model_registry import ModelCapabilities

    registry = FakeRegistry()
    registry._capabilities = {
        "openai/editor": ModelCapabilities(
            mode="image_generation", supported_endpoints=("/v1/images/edits",)
        ),
        "gemini/unknown-image": ModelCapabilities(mode="image_generation"),
    }
    suggestions = config_routes._build_role_suggestions(
        registry, ["openai/editor", "gemini/unknown-image"], {"openai", "gemini"}
    )
    assert suggestions["image_edit"] == ["openai/editor"]
    assert suggestions["_image_edit_unknown"] == ["gemini/unknown-image"]


def test_specialist_suggestions_require_configured_provider():
    from suzent.core.model_registry import ModelCapabilities

    registry = FakeRegistry()
    registry._capabilities = {
        f"{provider}/{mode}": ModelCapabilities(mode=mode)
        for provider in ("configured", "missing-key")
        for mode in (
            "embedding",
            "tts",
            "image_generation",
            "image_edit",
            "video_generation",
        )
    }
    suggestions = config_routes._build_role_suggestions(
        registry, ["missing-key/custom", "configured/custom"], {"configured"}
    )
    for role in (
        "embedding",
        "tts",
        "image_generation",
        "image_edit",
        "video_generation",
    ):
        assert suggestions[role] == [f"configured/{role}"]
    assert suggestions["_unregistered"] == ["configured/custom"]
    assert suggestions["_image_edit_unknown"] == ["configured/custom"]
    assert all(
        not models
        for models in config_routes._build_role_suggestions(
            registry, [], set()
        ).values()
    )


def test_configured_provider_ids_include_aliases_and_require_local_opt_in(monkeypatch):
    from suzent.core.providers import catalog, helpers

    def spec(name, keyless=False):
        return SimpleNamespace(
            id=name,
            aliases=[name + "-alias"],
            api_key_optional=keyless,
            env_keys=[] if keyless else ["TEST_KEY"],
            api_type="openai",
        )

    monkeypatch.setattr(
        catalog,
        "PROVIDER_REGISTRY",
        [
            spec("ready"),
            spec("missing"),
            spec("disabled"),
            spec("local", True),
            spec("unused-local", True),
        ],
    )
    monkeypatch.setattr(
        helpers,
        "resolve_api_key",
        lambda name: "test-key" if name in {"ready", "disabled"} else None,
    )
    monkeypatch.setattr(
        helpers,
        "_load_user_provider_config",
        lambda: {
            "disabled": {"enabled": False},
            "local": {"enabled_models": ["local/model"]},
        },
    )
    assert helpers.get_configured_provider_ids() == {
        "ready",
        "ready-alias",
        "local",
        "local-alias",
    }
