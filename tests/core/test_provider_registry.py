"""Tests for the data-driven provider registry (catalog.py)."""

import json
import pytest
from unittest.mock import patch

from suzent.core.providers.catalog import (
    OPENAI_COMPAT_PROVIDERS,
    PROVIDER_CONFIG,
    PROVIDER_CONFIG_BY_ID,
    PROVIDER_ENV_KEYS,
    PROVIDER_REGISTRY,
    PROVIDER_REGISTRY_BY_ID,
    ProviderSpec,
    _parse_provider,
    load_provider_registry,
)


class TestProviderSpec:
    """Tests for ProviderSpec dataclass."""

    def test_basic_creation(self):
        spec = ProviderSpec(
            id="test", label="Test", api_type="openai", env_keys=["TEST_KEY"]
        )
        assert spec.id == "test"
        assert spec.api_type == "openai"
        assert spec.is_compat is False
        assert spec.has_native_provider is False

    def test_compat_provider(self):
        spec = ProviderSpec(
            id="test",
            label="Test",
            api_type="openai",
            base_url="https://api.test.com/v1",
        )
        assert spec.is_compat is True

    def test_native_provider(self):
        spec = ProviderSpec(
            id="test",
            label="Test",
            api_type="openai",
            native_provider={
                "module": "pydantic_ai.providers.test",
                "class": "TestProvider",
            },
        )
        assert spec.has_native_provider is True
        assert spec.is_compat is False

    def test_frozen(self):
        spec = ProviderSpec(id="test", label="Test", api_type="openai")
        with pytest.raises(AttributeError):
            spec.id = "changed"


class TestParseProvider:
    """Tests for _parse_provider()."""

    def test_minimal_entry(self):
        raw = {"id": "test", "label": "Test Provider", "api_type": "openai"}
        spec = _parse_provider(raw)
        assert spec.id == "test"
        assert spec.env_keys == []
        assert spec.default_models == []
        assert spec.user_defined is False

    def test_full_entry(self):
        raw = {
            "id": "mycloud",
            "label": "My Cloud",
            "api_type": "anthropic",
            "base_url": "https://my-proxy.example.com/v1",
            "env_keys": ["MY_KEY"],
            "aliases": ["mc"],
            "native_provider": {"module": "test.mod", "class": "TestCls"},
            "fields": [{"key": "MY_KEY", "label": "Key", "type": "secret"}],
            "default_models": [{"id": "mycloud/m1", "name": "Model 1"}],
            "api_key_optional": True,
        }
        spec = _parse_provider(raw, user_defined=True)
        assert spec.api_type == "anthropic"
        assert spec.base_url == "https://my-proxy.example.com/v1"
        assert spec.aliases == ["mc"]
        assert spec.user_defined is True
        assert spec.is_compat is True
        assert spec.has_native_provider is True
        assert spec.api_key_optional is True


class TestRegistryLoading:
    """Tests for the module-level registry singletons."""

    def test_registry_not_empty(self):
        assert len(PROVIDER_REGISTRY) > 0

    def test_known_providers_exist(self):
        known = [
            "openai",
            "anthropic",
            "gemini",
            "xai",
            "deepseek",
            "ollama",
            "vllm",
            "sglang",
        ]
        for pid in known:
            assert pid in PROVIDER_REGISTRY_BY_ID, f"Missing provider: {pid}"

    def test_aliases_resolved(self):
        # "google" should alias to "gemini"
        assert "google" in PROVIDER_REGISTRY_BY_ID
        assert PROVIDER_REGISTRY_BY_ID["google"].id == "gemini"

        # "zai" should alias to "zhipuai"
        assert "zai" in PROVIDER_REGISTRY_BY_ID
        assert PROVIDER_REGISTRY_BY_ID["zai"].id == "zhipuai"

    def test_api_types_assigned(self):
        assert PROVIDER_REGISTRY_BY_ID["openai"].api_type == "openai"
        assert PROVIDER_REGISTRY_BY_ID["anthropic"].api_type == "anthropic"
        assert PROVIDER_REGISTRY_BY_ID["gemini"].api_type == "google"
        assert PROVIDER_REGISTRY_BY_ID["ollama"].api_type == "ollama"
        assert PROVIDER_REGISTRY_BY_ID["deepseek"].api_type == "openai"

    def test_native_providers_tagged(self):
        ds = PROVIDER_REGISTRY_BY_ID["deepseek"]
        assert ds.has_native_provider is True
        assert ds.native_provider["class"] == "DeepSeekProvider"

    def test_compat_providers_have_base_url(self):
        mm = PROVIDER_REGISTRY_BY_ID["minimax"]
        assert mm.is_compat is True
        assert "minimaxi.com" in mm.base_url

    def test_regions_default_to_the_base_url_and_have_a_field_to_write(self):
        """The first region is what an unset Base URL means, and picking any
        region writes the provider's *_BASE_URL field, so both must exist."""
        regional = [spec for spec in PROVIDER_REGISTRY if spec.regions]
        assert {"moonshot", "kimi_code", "zhipuai", "bailian_plan"} <= {
            spec.id for spec in regional
        }
        for spec in regional:
            assert spec.regions[0]["base_url"] == spec.base_url, spec.id
            assert any("BASE_URL" in f["key"] for f in spec.fields), spec.id
            ids = [region["id"] for region in spec.regions]
            assert len(ids) == len(set(ids)), spec.id
            assert spec.region_label in {"region", "plan"}, spec.id

    def test_regions_fill_in_a_missing_base_url(self):
        spec = _parse_provider(
            {
                "id": "x",
                "label": "X",
                "api_type": "openai",
                "regions": [{"id": "a", "name": "A", "base_url": "https://a.test/v1"}],
            }
        )
        assert spec.base_url == "https://a.test/v1"
        assert spec.region_label == "region"
        assert spec.split_accounts is False


class TestLegacyCompat:
    """Tests that legacy constants are correctly derived from the registry."""

    def test_provider_config_is_list_of_dicts(self):
        assert isinstance(PROVIDER_CONFIG, list)
        assert all(isinstance(e, dict) for e in PROVIDER_CONFIG)
        assert all("id" in e and "label" in e for e in PROVIDER_CONFIG)

    def test_provider_config_by_id(self):
        assert "openai" in PROVIDER_CONFIG_BY_ID
        assert PROVIDER_CONFIG_BY_ID["openai"]["label"] == "OpenAI"

    def test_provider_env_keys(self):
        assert PROVIDER_ENV_KEYS["openai"] == ["OPENAI_API_KEY"]
        assert "GEMINI_API_KEY" in PROVIDER_ENV_KEYS["gemini"]
        # Aliases
        assert PROVIDER_ENV_KEYS.get("google") == PROVIDER_ENV_KEYS.get("gemini")

    def test_openai_compat_providers(self):
        assert "minimax" in OPENAI_COMPAT_PROVIDERS
        assert "moonshot" in OPENAI_COMPAT_PROVIDERS
        # Alias
        assert "zai" in OPENAI_COMPAT_PROVIDERS
        # Native-only providers should NOT be in compat dict
        assert "openai" not in OPENAI_COMPAT_PROVIDERS
        assert "anthropic" not in OPENAI_COMPAT_PROVIDERS


class TestUserProviders:
    """Tests for user-defined provider loading."""

    def test_load_with_user_file(self, tmp_path):
        base = tmp_path / "providers.json"
        base.write_text(
            json.dumps(
                {"providers": [{"id": "base_p", "label": "Base", "api_type": "openai"}]}
            )
        )
        user = tmp_path / "providers.user.json"
        user.write_text(
            json.dumps(
                {
                    "providers": [
                        {"id": "user_p", "label": "Custom", "api_type": "anthropic"}
                    ]
                }
            )
        )

        with patch("suzent.core.providers.catalog._CONFIG_DIR", tmp_path):
            specs = load_provider_registry()

        ids = [s.id for s in specs]
        assert "base_p" in ids
        assert "user_p" in ids

        user_spec = next(s for s in specs if s.id == "user_p")
        assert user_spec.user_defined is True
        assert user_spec.api_type == "anthropic"

    def test_load_without_user_file(self, tmp_path):
        base = tmp_path / "providers.json"
        base.write_text(
            json.dumps(
                {
                    "providers": [
                        {"id": "only_base", "label": "Only", "api_type": "openai"}
                    ]
                }
            )
        )

        with patch("suzent.core.providers.catalog._CONFIG_DIR", tmp_path):
            specs = load_provider_registry()

        assert len(specs) == 1
        assert specs[0].id == "only_base"
