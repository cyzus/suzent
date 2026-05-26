"""Tests for ``get_default_chat_model`` — picks default from a configured provider."""

from __future__ import annotations

import pytest

from suzent.core.providers import helpers
from suzent.core.providers.catalog import ProviderSpec


def _spec(
    provider_id: str,
    *,
    env_key: str | None = "API_KEY",
    api_type: str = "openai",
    models: list[str] | None = None,
) -> ProviderSpec:
    return ProviderSpec(
        id=provider_id,
        label=provider_id.title(),
        api_type=api_type,
        env_keys=[env_key] if env_key else [],
        default_models=[{"id": m, "name": m} for m in (models or [])],
    )


@pytest.fixture
def catalog(monkeypatch):
    """Catalog ordered openai → anthropic → gemini, like the real one."""
    registry = [
        _spec(
            "openai", env_key="OPENAI_API_KEY", models=["openai/gpt-4.1", "openai/o3"]
        ),
        _spec(
            "anthropic",
            env_key="ANTHROPIC_API_KEY",
            models=["anthropic/claude-haiku-4-5"],
        ),
        _spec("gemini", env_key="GEMINI_API_KEY", models=["gemini/gemini-2.5-pro"]),
    ]
    monkeypatch.setattr(
        "suzent.core.providers.catalog.PROVIDER_REGISTRY", registry, raising=False
    )
    return registry


@pytest.fixture(autouse=True)
def _clear_cache():
    helpers.invalidate_default_model_cache()
    yield
    helpers.invalidate_default_model_cache()


@pytest.fixture
def no_user_config(monkeypatch):
    monkeypatch.setattr(helpers, "_load_user_provider_config", lambda: {})


def _set_configured(monkeypatch, configured_ids: set[str]) -> None:
    monkeypatch.setattr(
        helpers,
        "_provider_is_configured",
        lambda spec: spec.id in configured_ids,
    )


def test_returns_none_when_no_provider_configured(catalog, no_user_config, monkeypatch):
    _set_configured(monkeypatch, set())
    assert helpers.get_default_chat_model() is None


def test_prefers_first_configured_provider_in_catalog_order(
    catalog, no_user_config, monkeypatch
):
    # Only OpenAI has credentials — must not fall back to Anthropic alphabetically.
    _set_configured(monkeypatch, {"openai"})
    assert helpers.get_default_chat_model() == "openai/gpt-4.1"


def test_skips_unconfigured_providers_earlier_in_catalog(
    catalog, no_user_config, monkeypatch
):
    # OpenAI not configured, Anthropic is — must walk past OpenAI.
    _set_configured(monkeypatch, {"anthropic"})
    assert helpers.get_default_chat_model() == "anthropic/claude-haiku-4-5"


def test_user_enabled_models_take_precedence_over_catalog_defaults(
    catalog, monkeypatch
):
    _set_configured(monkeypatch, {"openai"})
    monkeypatch.setattr(
        helpers,
        "_load_user_provider_config",
        lambda: {"openai": {"enabled_models": ["openai/o3", "openai/gpt-4.1"]}},
    )
    assert helpers.get_default_chat_model() == "openai/o3"


def test_explicit_empty_enabled_models_skips_provider_when_blob_present(
    catalog, monkeypatch
):
    """When the blob exists, an empty enabled_models means 'this provider
    exposes no chat models' — must NOT fall back to catalog defaults, or
    `defaultModel` would point at a model that's absent from /config.models.
    Regression test for the case Scott flagged on PR #35.
    """
    _set_configured(monkeypatch, {"openai", "anthropic"})
    monkeypatch.setattr(
        helpers,
        "_load_user_provider_config",
        lambda: {
            "openai": {"enabled_models": []},
            "anthropic": {"enabled_models": ["anthropic/claude-haiku-4-5"]},
        },
    )
    assert helpers.get_default_chat_model() == "anthropic/claude-haiku-4-5"


def test_provider_configured_but_missing_from_blob_is_skipped(catalog, monkeypatch):
    """If the blob exists at all, it is the source of truth for which models
    are surfaced. A provider with credentials but no blob entry contributes
    no models to /config.models, so it must not yield a default either.
    """
    _set_configured(monkeypatch, {"openai", "anthropic"})
    monkeypatch.setattr(
        helpers,
        "_load_user_provider_config",
        lambda: {"anthropic": {"enabled_models": ["anthropic/claude-haiku-4-5"]}},
    )
    assert helpers.get_default_chat_model() == "anthropic/claude-haiku-4-5"


def test_returns_none_when_blob_present_but_all_enabled_lists_empty(
    catalog, monkeypatch
):
    _set_configured(monkeypatch, {"openai", "anthropic"})
    monkeypatch.setattr(
        helpers,
        "_load_user_provider_config",
        lambda: {
            "openai": {"enabled_models": []},
            "anthropic": {"enabled_models": []},
        },
    )
    assert helpers.get_default_chat_model() is None


def test_falls_back_to_catalog_default_only_when_blob_absent(catalog, monkeypatch):
    """No _PROVIDER_CONFIG_ saved (fresh install) is the only case where we
    use catalog default_models — matches get_enabled_models_from_db's
    fresh-install branch.
    """
    _set_configured(monkeypatch, {"openai"})
    monkeypatch.setattr(helpers, "_load_user_provider_config", lambda: {})
    assert helpers.get_default_chat_model() == "openai/gpt-4.1"


def test_provider_is_configured_uses_resolve_api_key_for_keyed_providers(
    catalog, monkeypatch
):
    spec = catalog[0]  # openai
    monkeypatch.setattr(
        helpers, "resolve_api_key", lambda pid: "sk-test" if pid == "openai" else None
    )
    assert helpers._provider_is_configured(spec) is True
    assert helpers._provider_is_configured(catalog[1]) is False


def test_load_user_provider_config_tolerates_malformed_blob(monkeypatch):
    class _FakeDB:
        def get_api_keys(self):
            return {"_PROVIDER_CONFIG_": "not-json{"}

    import suzent.database as db_mod

    monkeypatch.setattr(db_mod, "get_database", lambda: _FakeDB())
    assert helpers._load_user_provider_config() == {}
