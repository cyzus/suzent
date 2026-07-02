"""Tests for the model capabilities registry (model_registry.py)."""

import json
import pytest
from unittest.mock import patch

from suzent.core.model_registry import (
    ModelCapabilities,
    ModelRegistry,
    get_model_registry,
    prune_stale_models,
    save_discovered_models,
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
            patch(
                "suzent.core.model_registry._local_capabilities_dir",
                return_value=empty_dir,
            ),
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
            patch(
                "suzent.core.model_registry._local_capabilities_dir",
                return_value=empty_dir,
            ),
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
            patch(
                "suzent.core.model_registry._local_capabilities_dir",
                return_value=empty_dir,
            ),
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


class TestLocalOverlay:
    """The local overlay supplies discovered models without dirtying the
    shipped repo files; shipped curated entries always win."""

    def test_overlay_adds_models_not_shipped(self, tmp_path):
        shipped = tmp_path / "shipped"
        shipped.mkdir()
        (shipped / "acme.json").write_text(
            json.dumps({"models": {"acme/curated": {"mode": "chat"}}}),
            encoding="utf-8",
        )
        overlay = tmp_path / "overlay"
        overlay.mkdir()
        (overlay / "acme.json").write_text(
            json.dumps({"models": {"acme/discovered": {"mode": "chat"}}}),
            encoding="utf-8",
        )
        missing = tmp_path / "no_global.json"

        with (
            patch("suzent.core.model_registry._CAPABILITIES_DIR", shipped),
            patch("suzent.core.model_registry._CAPABILITIES_PATH", missing),
            patch(
                "suzent.core.model_registry._local_capabilities_dir",
                return_value=overlay,
            ),
        ):
            registry = ModelRegistry()

        assert registry.get_capabilities("acme/curated") is not None
        assert registry.get_capabilities("acme/discovered") is not None

    def test_shipped_wins_over_overlay_for_shared_id(self, tmp_path):
        shipped = tmp_path / "shipped"
        shipped.mkdir()
        (shipped / "acme.json").write_text(
            json.dumps(
                {"models": {"acme/m": {"mode": "chat", "max_input_tokens": 128000}}}
            ),
            encoding="utf-8",
        )
        overlay = tmp_path / "overlay"
        overlay.mkdir()
        # Stale bare stub for the same model — must not clobber curated data.
        (overlay / "acme.json").write_text(
            json.dumps({"models": {"acme/m": {"mode": "chat"}}}), encoding="utf-8"
        )
        missing = tmp_path / "no_global.json"

        with (
            patch("suzent.core.model_registry._CAPABILITIES_DIR", shipped),
            patch("suzent.core.model_registry._CAPABILITIES_PATH", missing),
            patch(
                "suzent.core.model_registry._local_capabilities_dir",
                return_value=overlay,
            ),
        ):
            registry = ModelRegistry()

        assert registry.get_context_window("acme/m") == 128000


class TestWriteTarget:
    """save_discovered_models routes writes to the overlay by default, or to
    the tracked repo dir in developer mode (SUZENT_CAPABILITIES_TO_REPO)."""

    def _models(self, path):
        return json.loads(path.read_text(encoding="utf-8"))["models"]

    def test_default_writes_to_overlay_not_repo(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SUZENT_CAPABILITIES_TO_REPO", raising=False)
        shipped = tmp_path / "shipped"
        shipped.mkdir()
        overlay = tmp_path / "overlay"

        with (
            patch("suzent.core.model_registry._CAPABILITIES_DIR", shipped),
            patch(
                "suzent.core.model_registry._local_capabilities_dir",
                return_value=overlay,
            ),
        ):
            save_discovered_models("acme", ["acme/found"])

        assert not (shipped / "acme.json").exists()
        assert "acme/found" in self._models(overlay / "acme.json")

    def test_dev_mode_writes_to_repo(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SUZENT_CAPABILITIES_TO_REPO", "1")
        shipped = tmp_path / "shipped"
        shipped.mkdir()
        overlay = tmp_path / "overlay"

        with (
            patch("suzent.core.model_registry._CAPABILITIES_DIR", shipped),
            patch(
                "suzent.core.model_registry._local_capabilities_dir",
                return_value=overlay,
            ),
        ):
            save_discovered_models("acme", ["acme/found"])

        assert "acme/found" in self._models(shipped / "acme.json")
        assert not overlay.exists()


class TestPruneStaleModels:
    """Tests for prune_stale_models — automatic deprecation cleanup."""

    def _write(self, tmp_path, provider_id, models):
        """Write a provider file into the *local overlay* dir (where prune now
        operates). No shipped repo file exists for these providers, so prune
        sees only the overlay."""
        cap_dir = tmp_path / "capabilities"
        cap_dir.mkdir(exist_ok=True)
        (cap_dir / f"{provider_id}.json").write_text(
            json.dumps({"models": models}), encoding="utf-8"
        )
        return cap_dir

    def _read(self, cap_dir, provider_id):
        return json.loads(
            (cap_dir / f"{provider_id}.json").read_text(encoding="utf-8")
        )["models"]

    def test_removes_stale_stub(self, tmp_path):
        cap_dir = self._write(
            tmp_path,
            "acme",
            {"acme/new": {"mode": "chat"}, "acme/old": {"mode": "chat"}},
        )
        with patch(
            "suzent.core.model_registry._local_capabilities_dir", return_value=cap_dir
        ):
            removed = prune_stale_models("acme", ["acme/new"])

        assert removed == ["acme/old"]
        assert set(self._read(cap_dir, "acme")) == {"acme/new"}

    def test_keeps_curated_entry_even_if_absent(self, tmp_path):
        cap_dir = self._write(
            tmp_path,
            "acme",
            {
                "acme/curated": {"mode": "chat", "max_input_tokens": 128000},
                "acme/stub": {"mode": "chat"},
            },
        )
        with patch(
            "suzent.core.model_registry._local_capabilities_dir", return_value=cap_dir
        ):
            removed = prune_stale_models("acme", ["acme/something-else"])

        assert removed == ["acme/stub"]
        assert "acme/curated" in self._read(cap_dir, "acme")

    def test_empty_live_list_is_noop(self, tmp_path):
        cap_dir = self._write(tmp_path, "acme", {"acme/old": {"mode": "chat"}})
        with patch(
            "suzent.core.model_registry._local_capabilities_dir", return_value=cap_dir
        ):
            removed = prune_stale_models("acme", [])

        assert removed == []
        assert "acme/old" in self._read(cap_dir, "acme")

    def test_missing_file_returns_empty(self, tmp_path):
        cap_dir = tmp_path / "capabilities"
        cap_dir.mkdir()
        with patch(
            "suzent.core.model_registry._local_capabilities_dir", return_value=cap_dir
        ):
            assert prune_stale_models("nope", ["nope/x"]) == []
