"""Selection and loading of generated provider defaults."""

import json
import runpy
from pathlib import Path

from suzent.core.providers import catalog


select_default_models = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "scripts/sync_model_defaults.py")
)["select_default_models"]


def test_selects_recent_chat_models_without_snapshots() -> None:
    raw = {
        "claude-sonnet-5-5": {"litellm_provider": "anthropic", "mode": "chat"},
        "claude-sonnet-5-5-20261001": {
            "litellm_provider": "anthropic",
            "mode": "chat",
        },
        "claude-sonnet-4-6": {"litellm_provider": "anthropic", "mode": "chat"},
        "zai/glm-5.3": {"mode": "chat"},
        "zai/glm-5.3-flash": {"mode": "chat"},
        "xiaomi_mimo/mimo-v2.6-pro": {"mode": "chat"},
        "xiaomi_mimo/mimo-v2.6-pro-ultraspeed": {"mode": "chat"},
        "xiaomi_mimo/mimo-v2.6-flash": {"mode": "image_generation"},
        "xai/grok-4.20": {"mode": "chat"},
        "xai/grok-4.7": {"mode": "chat"},
        "xai/grok-4.6": {"mode": "chat"},
    }

    selected = select_default_models(raw)

    assert [model["id"] for model in selected["anthropic"]] == [
        "anthropic/claude-sonnet-5-5"
    ]
    assert [model["id"] for model in selected["zhipuai"]] == [
        "zai/glm-5.3",
        "zai/glm-5.3-flash",
    ]
    assert [model["id"] for model in selected["xiaomi_mimo"]] == [
        "xiaomi_mimo/mimo-v2.6-pro"
    ]
    assert [model["id"] for model in selected["xai"]] == [
        "xai/grok-4.7",
        "xai/grok-4.6",
    ]


def test_generated_defaults_override_builtin_catalog(tmp_path, monkeypatch) -> None:
    (tmp_path / "providers.json").write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "anthropic",
                        "label": "Anthropic",
                        "api_type": "anthropic",
                        "default_models": [
                            {"id": "anthropic/claude-sonnet-4-6", "name": "Old"}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "provider_defaults.json").write_text(
        json.dumps(
            {
                "anthropic": [
                    {"id": "anthropic/claude-sonnet-5-5", "name": "Claude Sonnet 5.5"}
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(catalog, "_CONFIG_DIR", tmp_path)

    specs = catalog.load_provider_registry()

    assert specs[0].default_models == [
        {"id": "anthropic/claude-sonnet-5-5", "name": "Claude Sonnet 5.5"}
    ]
