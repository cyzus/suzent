from suzent.core.providers.helpers import get_enabled_models_from_db


def test_get_enabled_models_from_db_uses_config_fallback(monkeypatch):
    from suzent.config import CONFIG

    monkeypatch.setattr(
        "suzent.core.providers.helpers._load_user_provider_config",
        lambda: None,
    )
    monkeypatch.setattr(CONFIG, "model_options", ["openai/gpt-4.1"])

    assert get_enabled_models_from_db() == ["openai/gpt-4.1"]
