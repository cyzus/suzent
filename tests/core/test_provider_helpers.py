from suzent.core.providers.helpers import get_effective_enabled_models


def test_get_effective_enabled_models_uses_config_fallback(monkeypatch):
    from suzent.config import CONFIG

    monkeypatch.setattr(
        "suzent.core.providers.helpers.get_enabled_models_from_db",
        lambda: [],
    )
    monkeypatch.setattr(CONFIG, "model_options", ["openai/gpt-4.1"])

    assert get_effective_enabled_models() == ["openai/gpt-4.1"]
