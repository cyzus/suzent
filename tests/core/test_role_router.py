"""Tests for the role-based model router."""

import pytest

from suzent.core.role_router import ModelRole, RoleConfig, RoleRouter


class TestRoleConfig:
    def test_primary_model_id(self):
        rc = RoleConfig(["openai/gpt-4.1", "anthropic/claude-sonnet-4-6"])
        assert rc.primary_model_id == "openai/gpt-4.1"

    def test_empty_returns_none(self):
        rc = RoleConfig([])
        assert rc.primary_model_id is None


class TestModelRole:
    def test_enum_values(self):
        assert ModelRole.PRIMARY == "primary"
        assert ModelRole.CHEAP == "cheap"
        assert ModelRole.VISION == "vision"
        assert ModelRole.TTS == "tts"
        assert ModelRole.EMBEDDING == "embedding"
        assert ModelRole.IMAGE_GENERATION == "image_generation"


class TestRoleRouter:
    def test_set_and_get(self):
        router = RoleRouter()
        router.set_role("primary", ["openai/gpt-4.1"])
        assert router.get_model_id("primary") == "openai/gpt-4.1"

    def test_get_model_ids(self):
        router = RoleRouter()
        router.set_role("primary", ["openai/gpt-4.1", "anthropic/claude-sonnet-4-6"])
        ids = router.get_model_ids("primary")
        assert ids == ["openai/gpt-4.1", "anthropic/claude-sonnet-4-6"]

    def test_get_unset_role_returns_none(self):
        router = RoleRouter()
        assert router.get_model_id("nonexistent") is None

    def test_get_model_ids_unset_returns_empty(self):
        router = RoleRouter()
        assert router.get_model_ids("nonexistent") == []

    def test_has_role(self):
        router = RoleRouter()
        assert router.has_role("primary") is False
        router.set_role("primary", ["openai/gpt-4.1"])
        assert router.has_role("primary") is True

    def test_list_roles(self):
        router = RoleRouter()
        router.set_role("primary", ["model-a"])
        router.set_role("cheap", ["model-b", "model-c"])
        roles = router.list_roles()
        assert roles == {
            "primary": ["model-a"],
            "cheap": ["model-b", "model-c"],
        }

    def test_resolve_raises_on_empty(self):
        router = RoleRouter()
        with pytest.raises(ValueError, match="No models configured"):
            router.resolve("primary")

    def test_load_from_dict_nested(self):
        router = RoleRouter()
        router.load_from_dict(
            {
                "primary": {"models": ["openai/gpt-4.1"]},
                "cheap": {"models": ["openai/gpt-4.1-mini", "gemini/gemini-2.0-flash"]},
            }
        )
        assert router.get_model_id("primary") == "openai/gpt-4.1"
        assert router.get_model_ids("cheap") == [
            "openai/gpt-4.1-mini",
            "gemini/gemini-2.0-flash",
        ]

    def test_load_from_dict_simplified(self):
        router = RoleRouter()
        router.load_from_dict(
            {
                "primary": ["openai/gpt-4.1"],
                "tts": ["gemini/gemini-2.5-flash-preview-tts"],
            }
        )
        assert router.get_model_id("primary") == "openai/gpt-4.1"
        assert router.get_model_id("tts") == "gemini/gemini-2.5-flash-preview-tts"

    def test_overwrite_role(self):
        router = RoleRouter()
        router.set_role("primary", ["model-a"])
        router.set_role("primary", ["model-b"])
        assert router.get_model_id("primary") == "model-b"

    def test_load_from_dict_ignores_empty(self):
        router = RoleRouter()
        router.load_from_dict(
            {
                "primary": {"models": []},
                "cheap": [],
            }
        )
        assert router.has_role("primary") is False
        assert router.has_role("cheap") is False
