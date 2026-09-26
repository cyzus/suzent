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

    def test_load_from_dict_preserves_empty(self):
        router = RoleRouter()
        router.load_from_dict(
            {
                "primary": {"models": []},
                "cheap": [],
            }
        )
        assert router.has_role("primary") is False
        assert router.has_role("cheap") is False

    def test_replace_from_dict_clears_existing_roles(self):
        router = RoleRouter()
        router.set_role("primary", ["openai/gpt-4.1"])
        router.set_role("cheap", ["openai/gpt-4.1-mini"])

        router.replace_from_dict({"primary": []})

        assert router.list_roles() == {"primary": []}

    def test_load_from_config_ignores_legacy_model_fields(self, monkeypatch):
        from suzent import config as config_mod

        monkeypatch.setattr(config_mod.CONFIG, "role_models", {}, raising=False)
        monkeypatch.setattr(
            config_mod.CONFIG,
            "embedding_model",
            "gemini/gemini-embedding-001",
            raising=False,
        )
        monkeypatch.setattr(
            config_mod.CONFIG,
            "extraction_model",
            "gemini/gemini-2.5-flash",
            raising=False,
        )

        router = RoleRouter()
        router.load_from_config()

        assert router.list_roles() == {}


@pytest.mark.parametrize(
    "role",
    ["title", "memory_extraction", "decision", "goal_judge", "permission_review"],
)
def test_task_roles_inherit_nearest_configured_chain(role: str) -> None:
    router = RoleRouter()
    router.set_role("primary", ["primary-a", "primary-b"])
    assert router.get_model_ids(role) == ["primary-a", "primary-b"]
    router.set_role("cheap", ["cheap-a", "cheap-b"])
    assert router.get_model_ids(role) == ["cheap-a", "cheap-b"]
    router.set_role(role, ["override"])
    assert router.get_model_ids(role) == ["override"]
    router.set_role(role, [])
    assert router.get_model_ids(role) == ["cheap-a", "cheap-b"]


@pytest.mark.parametrize("role", ["goal_judge", "permission_review"])
def test_decision_children_inherit_without_affecting_other_tasks(role: str) -> None:
    router = RoleRouter()
    router.set_role("cheap", ["lightweight"])
    router.set_role("decision", ["judge-a", "judge-b"])
    assert router.get_model_ids(role) == ["judge-a", "judge-b"]
    assert router.get_model_id("title") == "lightweight"
    assert router.get_model_id("memory_extraction") == "lightweight"
    router.set_role(role, ["specialist"])
    assert router.get_model_ids(role) == ["specialist"]
    assert router.get_model_ids("decision") == ["judge-a", "judge-b"]


def test_dream_inherits_primary_instead_of_cheap() -> None:
    router = RoleRouter()
    router.set_role("primary", ["agent"])
    router.set_role("cheap", ["lightweight"])
    assert router.get_model_ids("dream") == ["agent"]


@pytest.mark.parametrize("explicit", [None, "selected-dream"])
def test_legacy_dream_config_is_used_only_without_explicit_role(
    monkeypatch, explicit: str | None
) -> None:
    from suzent.config import CONFIG

    monkeypatch.setattr(CONFIG, "role_models", {})
    monkeypatch.setattr(CONFIG, "memory_consolidation_model", "legacy-dream")
    router = RoleRouter()
    if explicit:
        router.set_role("dream", [explicit])
    router.load_from_config()
    assert router.get_model_id("dream") == (explicit or "legacy-dream")


def test_saved_roles_take_precedence_over_yaml_defaults(monkeypatch) -> None:
    from suzent.config import CONFIG

    monkeypatch.setattr(
        CONFIG, "role_models", {"decision": ["yaml"], "dream": ["yaml-dream"]}
    )
    monkeypatch.setattr(CONFIG, "memory_consolidation_model", "legacy-dream")
    router = RoleRouter()
    router.set_role("decision", ["saved"])
    router.load_from_config()
    assert router.get_model_id("goal_judge") == "saved"
    assert router.get_model_id("dream") == "yaml-dream"


def test_new_roles_survive_serialization_and_clearing() -> None:
    router = RoleRouter()
    router.load_from_dict(
        {"decision": {"models": ["judge"]}, "permission_review": ["reviewer"]}
    )
    restored = RoleRouter()
    restored.replace_from_dict(router.list_roles())
    assert restored.get_model_id("permission_review") == "reviewer"
    restored.replace_from_dict({"decision": ["judge"], "permission_review": []})
    assert restored.get_model_id("permission_review") == "judge"


def test_cleared_roles_survive_db_restart_and_config_defaults(monkeypatch) -> None:
    import json
    from types import SimpleNamespace
    from suzent.config import CONFIG

    saved: dict[str, str] = {}
    db = SimpleNamespace(
        save_api_key=lambda key, value: saved.update({key: value}),
        get_api_keys=lambda: saved,
    )
    monkeypatch.setattr("suzent.database.get_database", lambda: db)
    monkeypatch.setenv("_ROLE_MODELS_", "")
    monkeypatch.setattr(
        CONFIG,
        "role_models",
        {
            "memory_extraction": ["yaml-extractor"],
            "decision": ["yaml-decision"],
            "title": ["yaml-title"],
        },
    )
    monkeypatch.setattr(CONFIG, "memory_consolidation_model", "legacy-dream")
    router = RoleRouter()
    router.replace_from_dict(
        {
            "primary": ["main"],
            "cheap": ["lightweight"],
            "memory_extraction": [],
            "decision": [],
            "dream": [],
        }
    )
    router.save_to_db()
    assert json.loads(saved["_ROLE_MODELS_"])["dream"] == {"models": []}

    restarted = RoleRouter()
    restarted.load_from_db()
    restarted.load_from_config()
    assert restarted.list_roles()["memory_extraction"] == []
    assert restarted.get_model_id("memory_extraction") == "lightweight"
    assert restarted.get_model_id("goal_judge") == "lightweight"
    assert restarted.get_model_id("dream") == "main"
    assert restarted.get_model_id("title") == "yaml-title"
