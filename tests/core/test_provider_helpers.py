from suzent.core.providers import helpers
from suzent.core.providers.catalog import ProviderSpec
from suzent.core.providers.helpers import get_enabled_models_from_db


def test_get_enabled_models_from_db_uses_config_fallback(monkeypatch):
    from suzent.config import CONFIG

    monkeypatch.setattr(
        "suzent.core.providers.helpers._load_user_provider_config",
        lambda: None,
    )
    monkeypatch.setattr(CONFIG, "model_options", ["openai/gpt-4.1"])

    assert get_enabled_models_from_db() == ["openai/gpt-4.1"]


def test_get_enabled_models_from_db_includes_configured_provider_models(monkeypatch):
    spec = ProviderSpec(
        id="openai",
        label="OpenAI",
        api_type="openai",
        env_keys=["OPENAI_API_KEY"],
        default_models=[{"id": "openai/gpt-4.1", "name": "gpt-4.1"}],
    )
    monkeypatch.setattr(
        "suzent.core.providers.catalog.PROVIDER_REGISTRY", [spec], raising=False
    )
    monkeypatch.setattr(helpers, "_load_user_provider_config", lambda: {})
    monkeypatch.setattr(helpers, "_provider_is_configured", lambda s: s.id == "openai")
    monkeypatch.setattr(
        "suzent.core.model_registry.list_provider_chat_models",
        lambda pid: ["openai/gpt-4.1", "openai/o4-mini"] if pid == "openai" else [],
    )

    models = get_enabled_models_from_db()
    assert "openai/gpt-4.1" in models
    assert "openai/o4-mini" in models


def test_get_enabled_models_from_db_respects_explicit_empty_enabled_models(monkeypatch):
    spec = ProviderSpec(
        id="openai",
        label="OpenAI",
        api_type="openai",
        env_keys=["OPENAI_API_KEY"],
        default_models=[{"id": "openai/gpt-4.1", "name": "gpt-4.1"}],
    )
    monkeypatch.setattr(
        "suzent.core.providers.catalog.PROVIDER_REGISTRY", [spec], raising=False
    )
    monkeypatch.setattr(
        helpers,
        "_load_user_provider_config",
        lambda: {"openai": {"enabled_models": []}},
    )
    monkeypatch.setattr(helpers, "_provider_is_configured", lambda s: True)
    monkeypatch.setattr(
        "suzent.core.model_registry.list_provider_chat_models",
        lambda pid: ["openai/gpt-4.1"],
    )

    assert get_enabled_models_from_db() == []


def test_normalize_provider_model_id_prefixes_bare_models_and_drops_provider_name(
    monkeypatch,
):
    spec = ProviderSpec(
        id="gemini",
        label="Gemini",
        api_type="google",
        env_keys=["GEMINI_API_KEY"],
        default_models=[{"id": "gemini/gemini-2.5-pro", "name": "gemini-2.5-pro"}],
    )
    monkeypatch.setattr(
        "suzent.core.providers.catalog.PROVIDER_REGISTRY", [spec], raising=False
    )
    monkeypatch.setattr(
        helpers,
        "_load_user_provider_config",
        lambda: {
            "gemini": {
                "enabled_models": ["Gemini", "gemini-exp-custom"],
                "custom_models": ["Gemini", "gemini-exp-custom"],
            }
        },
    )
    monkeypatch.setattr(helpers, "_provider_is_configured", lambda s: False)

    models = get_enabled_models_from_db()
    assert "Gemini" not in models
    assert "gemini/Gemini" not in models
    assert models == ["gemini/gemini-exp-custom"]


def test_starred_models_returns_normalized_user_starred_list(monkeypatch):
    spec = ProviderSpec(
        id="gemini",
        label="Gemini",
        api_type="google",
        env_keys=["GEMINI_API_KEY"],
        default_models=[{"id": "gemini/gemini-2.5-pro", "name": "gemini-2.5-pro"}],
    )
    monkeypatch.setattr(
        "suzent.core.providers.catalog.PROVIDER_REGISTRY", [spec], raising=False
    )
    monkeypatch.setattr(
        helpers,
        "_load_user_provider_config",
        lambda: {"gemini": {"starred_models": ["gemini/gemini-4-argon", "Gemini"]}},
    )

    assert helpers.get_starred_models_from_db() == ["gemini/gemini-4-argon"]
