"""Tests for the model capabilities registry (model_registry.py)."""

import json
import pytest
from unittest.mock import patch

from suzent.core.model_registry import (
    ModelCapabilities,
    ModelRegistry,
    get_model_registry,
)


class TestModelCapabilities:
    """Tests for the ModelCapabilities dataclass."""

    def test_defaults(self):
        caps = ModelCapabilities()
        assert caps.mode == "chat"
        assert caps.max_input_tokens == 0
        assert caps.supports_vision is False
        assert caps.context_window == 0

    def test_context_window(self):
        caps = ModelCapabilities(max_input_tokens=100000, max_output_tokens=8000)
        assert caps.context_window == 108000

    def test_estimate_cost(self):
        caps = ModelCapabilities(
            input_cost_per_token=3e-06,
            output_cost_per_token=1.5e-05,
        )
        cost = caps.estimate_cost(100000, 5000)
        expected = 100000 * 3e-06 + 5000 * 1.5e-05
        assert abs(cost - expected) < 1e-10

    def test_frozen(self):
        caps = ModelCapabilities()
        with pytest.raises(AttributeError):
            caps.mode = "embedding"


class TestModelRegistryFromFile:
    """Tests for ModelRegistry loading from a real JSON file."""

    def test_loads_from_project_config(self):
        registry = get_model_registry()
        # Should have loaded at least some models
        assert len(registry.list_models()) > 0

    def test_known_model_lookup(self):
        registry = get_model_registry()
        caps = registry.get_capabilities("openai/gpt-4.1")
        assert caps is not None
        assert caps.mode == "chat"
        assert caps.max_input_tokens > 0
        assert caps.supports_vision is True
        assert caps.supports_function_calling is True

    def test_unknown_model_returns_none(self):
        registry = get_model_registry()
        assert registry.get_capabilities("nonexistent/model") is None

    def test_context_window_shortcut(self):
        registry = get_model_registry()
        window = registry.get_context_window("gemini/gemini-2.5-pro")
        assert window > 0

    def test_context_window_unknown(self):
        registry = get_model_registry()
        assert registry.get_context_window("nonexistent/model") == 0

    def test_supports_vision_shortcut(self):
        registry = get_model_registry()
        assert registry.supports_vision("anthropic/claude-sonnet-4-6") is True
        assert registry.supports_vision("deepseek/deepseek-chat") is False

    def test_supports_reasoning_shortcut(self):
        registry = get_model_registry()
        assert registry.supports_reasoning("openai/o3") is True
        assert registry.supports_reasoning("openai/gpt-4.1") is False

    def test_list_models_by_mode(self):
        registry = get_model_registry()
        chat_models = registry.list_models(mode="chat")
        assert len(chat_models) > 0
        assert all(registry.get_capabilities(m).mode == "chat" for m in chat_models)


class TestModelRegistryCustomJSON:
    """Tests with a custom JSON file."""

    def test_load_custom_file(self, tmp_path):
        caps_file = tmp_path / "model_capabilities.json"
        caps_file.write_text(
            json.dumps(
                {
                    "_schema_version": "1.0",
                    "models": {
                        "custom/my-model": {
                            "mode": "embedding",
                            "max_input_tokens": 512,
                            "output_vector_size": 768,
                        }
                    },
                }
            )
        )

        with patch("suzent.core.model_registry._CAPABILITIES_PATH", caps_file):
            registry = ModelRegistry()

        caps = registry.get_capabilities("custom/my-model")
        assert caps is not None
        assert caps.mode == "embedding"
        assert caps.output_vector_size == 768

    def test_missing_file_returns_empty(self, tmp_path):
        missing = tmp_path / "does_not_exist.json"
        empty_dir = tmp_path / "capabilities"  # doesn't exist → no per-provider files

        with (
            patch("suzent.core.model_registry._CAPABILITIES_PATH", missing),
            patch("suzent.core.model_registry._CAPABILITIES_DIR", empty_dir),
        ):
            registry = ModelRegistry()

        assert len(registry.list_models()) == 0

    def test_malformed_json_returns_empty(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json")
        empty_dir = tmp_path / "capabilities"

        with (
            patch("suzent.core.model_registry._CAPABILITIES_PATH", bad_file),
            patch("suzent.core.model_registry._CAPABILITIES_DIR", empty_dir),
        ):
            registry = ModelRegistry()

        assert len(registry.list_models()) == 0

    def test_reload(self, tmp_path):
        caps_file = tmp_path / "model_capabilities.json"
        caps_file.write_text(
            json.dumps(
                {"_schema_version": "1.0", "models": {"test/m1": {"mode": "chat"}}}
            )
        )
        empty_dir = tmp_path / "capabilities"

        with (
            patch("suzent.core.model_registry._CAPABILITIES_PATH", caps_file),
            patch("suzent.core.model_registry._CAPABILITIES_DIR", empty_dir),
        ):
            registry = ModelRegistry()
            assert len(registry.list_models()) == 1

            # Update file
            caps_file.write_text(
                json.dumps(
                    {
                        "_schema_version": "1.0",
                        "models": {
                            "test/m1": {"mode": "chat"},
                            "test/m2": {"mode": "embedding"},
                        },
                    }
                )
            )
            registry.reload()
            assert len(registry.list_models()) == 2
