"""
Configuration-related API routes.

Handles configuration endpoints that provide frontend-consumable
application settings including user preferences, API keys, and provider management.
"""

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.config import CONFIG
from suzent.core.provider_factory import (
    PROVIDER_CONFIG,
    ProviderFactory,
    get_enabled_models_from_db,
)
from suzent.database import get_database


def get_resource_path(path: str) -> Path:
    """Get absolute path to resource, working for dev and PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller
        base_path = Path(sys._MEIPASS)
    else:
        # Dev (relative to project root? or CWD?)
        # If running from suzent root, CWD is root.
        base_path = Path(".")

    return base_path / path


async def get_config(request: Request) -> JSONResponse:
    """Return frontend-consumable configuration merged with user preferences."""
    db = get_database()
    user_prefs = db.get_user_preferences()

    sandbox_enabled = getattr(CONFIG, "sandbox_enabled", False)
    sandbox_volumes = CONFIG.sandbox_volumes or []
    available_models = get_enabled_models_from_db()

    # Get embedding/extraction models with fallback to CONFIG defaults
    from suzent.core.provider_factory import get_effective_memory_config

    mem_config = get_effective_memory_config()
    embedding_model = mem_config["embedding_model"]
    extraction_model = mem_config["extraction_model"]

    data: dict[str, Any] = {
        "title": CONFIG.title,
        "models": available_models,
        "agents": CONFIG.agent_options,
        "tools": [t for t in CONFIG.tool_options if t != "SkillTool"],
        "defaultTools": [t for t in CONFIG.default_tools if t != "SkillTool"],
        "codeTag": CONFIG.code_tag,
        "userId": CONFIG.user_id,
        "globalSandboxVolumes": sandbox_volumes,
        "sandboxEnabled": sandbox_enabled,
        "embeddingModel": CONFIG.embedding_model,
        "extractionModel": CONFIG.extraction_model,
    }

    if user_prefs:
        data["userPreferences"] = {
            "model": user_prefs.model,
            "agent": user_prefs.agent,
            "tools": user_prefs.tools,
            "memory_enabled": user_prefs.memory_enabled,
            "sandbox_enabled": user_prefs.sandbox_enabled,
            "sandbox_volumes": user_prefs.sandbox_volumes,
            "embedding_model": embedding_model,
            "extraction_model": extraction_model,
        }
    else:
        # Even if no user_prefs, provide memory config defaults
        data["userPreferences"] = {
            "embedding_model": embedding_model,
            "extraction_model": extraction_model,
        }

    return JSONResponse(data)


async def save_preferences(request: Request) -> JSONResponse:
    """Save user preferences to the database."""
    data = await request.json()

    db = get_database()

    # Save user preferences (non-memory settings)
    success = db.save_user_preferences(
        model=data.get("model"),
        agent=data.get("agent"),
        tools=data.get("tools"),
        memory_enabled=data.get("memory_enabled"),
        sandbox_enabled=data.get("sandbox_enabled"),
        sandbox_volumes=data.get("sandbox_volumes"),
    )

    # Save memory configuration separately
    if (
        data.get("embedding_model") is not None
        or data.get("extraction_model") is not None
    ):
        db.save_memory_config(
            embedding_model=data.get("embedding_model"),
            extraction_model=data.get("extraction_model"),
        )

    if success:
        return JSONResponse({"success": True})
    return JSONResponse({"error": "Failed to save preferences"}, status_code=500)


async def get_api_keys_status(request: Request) -> JSONResponse:
    """Get configured providers and their status with masked secrets."""
    try:
        db = get_database()
        api_keys = db.get_api_keys() or {}

        provider_config_blob = api_keys.get("_PROVIDER_CONFIG_")
        custom_config: dict[str, Any] = {}
        if provider_config_blob:
            try:
                custom_config = json.loads(provider_config_blob)
            except json.JSONDecodeError:
                pass

        providers = []
        for provider_def in PROVIDER_CONFIG:
            provider_id = provider_def["id"]
            user_conf = custom_config.get(provider_id, {})

            provider_data: dict[str, Any] = {
                "id": provider_id,
                "label": provider_def["label"],
                "default_models": provider_def.get("default_models", []),
                "fields": [],
                "models": [],
            }

            for field in provider_def["fields"]:
                key = field["key"]
                val = api_keys.get(key)
                source = "db" if val else None

                if not val and os.environ.get(key):
                    val = os.environ.get(key)
                    source = "env"

                display_val = ""
                if val:
                    if field["type"] == "secret":
                        if source == "env":
                            display_val = (
                                "Set in env"
                                if len(val) < 8
                                else f"{val[:4]}...{val[-4:]} (env)"
                            )
                        else:
                            display_val = "********"
                    else:
                        display_val = val

                provider_data["fields"].append(
                    {
                        "key": key,
                        "label": field["label"],
                        "placeholder": field["placeholder"],
                        "type": field["type"],
                        "value": display_val,
                        "isSet": bool(val),
                    }
                )

            enabled_models = set(user_conf.get("enabled_models", []))
            custom_models_list = user_conf.get("custom_models", [])

            provider_data["user_config"] = {
                "enabled_models": list(enabled_models),
                "custom_models": custom_models_list,
            }

            providers.append(provider_data)

        return JSONResponse({"providers": providers})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def save_api_keys(request: Request) -> JSONResponse:
    """Save API keys to database and inject into runtime environment."""
    try:
        data = await request.json()
        keys = data.get("keys", {})

        db = get_database()
        count = 0

        for key, value in keys.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue

            # Skip masked values that weren't changed
            if "..." in value and "(env)" in value:
                continue

            if not value:
                db.delete_api_key(key)
                if key in os.environ:
                    del os.environ[key]
            else:
                db.save_api_key(key, value)
                os.environ[key] = value
                count += 1

        return JSONResponse({"success": True, "updated": count})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def verify_provider(request: Request) -> JSONResponse:
    """Verify provider credentials and fetch available models."""
    try:
        provider_id = request.path_params["provider_id"]
        data = await request.json()
        config = data.get("config", {})

        try:
            provider = ProviderFactory.get_provider(provider_id, config)
        except ValueError:
            return JSONResponse(
                {"error": f"Provider {provider_id} not supported"},
                status_code=400,
            )

        models = await provider.list_models()
        success = await provider.validate_credentials()

        return JSONResponse(
            {
                "success": success,
                "models": [m.model_dump() for m in models],
            }
        )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_embedding_models(request: Request) -> JSONResponse:
    """
    Fetch available embedding models from configured providers.

    Uses LiteLLM's get_valid_models() with provider endpoint checking,
    then filters for models containing 'embedding' in the name.
    """
    try:
        import litellm

        # Fetch valid models from all configured providers
        all_models = litellm.get_valid_models(check_provider_endpoint=True)

        # Filter for embedding models
        embedding_models = [
            model for model in all_models if "embedding" in model.lower()
        ]

        # Sort for consistent ordering
        embedding_models.sort()

        return JSONResponse({"models": embedding_models})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": str(e), "models": []}, status_code=500)


def _mask_social_config(config: dict) -> dict:
    """Recursively mask secret fields in the configuration."""
    masked = {}
    for key, value in config.items():
        if isinstance(value, dict):
            masked[key] = _mask_social_config(value)
        elif (
            isinstance(value, str)
            and any(s in key.lower() for s in ["token", "secret", "password", "key"])
            and "public" not in key.lower()
            and key != "key"
        ):  # "key" might be generic, but let's be safe. key usually implies secret.
            # allowed_users doesn't match 'key'/'secret' etc.
            # But wait, 'encrypt_key', 'app_secret', 'bot_token'
            if value:
                masked[key] = "********"
            else:
                masked[key] = value
        else:
            masked[key] = value
    return masked


def _merge_social_config(existing: dict, incoming: dict):
    """Recursively merge incoming config into existing, ignoring masked values."""
    for key, value in incoming.items():
        if isinstance(value, dict):
            if key not in existing or not isinstance(existing[key], dict):
                existing[key] = {}
            _merge_social_config(existing[key], value)
        else:
            # If value is the mask, keep existing value
            if value == "********":
                continue
            existing[key] = value


async def get_social_config(request: Request) -> JSONResponse:
    """Get the current social configuration."""
    try:
        from pathlib import Path

        # Assuming social config is in config/social.json
        config_path = Path("config/social.json")
        if not config_path.exists():
            return JSONResponse({"config": {}})

        with open(config_path, "r") as f:
            config = json.load(f)

        with open(config_path, "r") as f:
            config = json.load(f)

        # Load defaults from example file to ensure all platforms are visible
        # This keeps it DRY by using the example file as the source of truth
        defaults_path = get_resource_path("config/social.example.json")
        if defaults_path.exists():
            try:
                with open(defaults_path, "r") as f:
                    defaults = json.load(f)

                import copy

                # Iterate over defaults (which includes all supported platforms)
                for key, default_settings in defaults.items():
                    # Skip top-level non-platform keys
                    if not isinstance(default_settings, dict):
                        continue

                    # Prepare sanitized default (disabled by default)
                    sanitized_default = copy.deepcopy(default_settings)
                    if "enabled" in sanitized_default:
                        sanitized_default["enabled"] = False

                    if key not in config:
                        config[key] = sanitized_default
                    elif isinstance(config[key], dict):
                        # Ensure all default fields exist
                        for k, v in sanitized_default.items():
                            if k not in config[key]:
                                config[key][k] = v
            except Exception as e:
                # Log but continue if defaults load fails
                print(f"Failed to load social defaults: {e}")

        masked_config = _mask_social_config(config)

        # Include active model from memory if available
        active_model = None
        if (
            hasattr(request.app.state, "social_brain")
            and request.app.state.social_brain
        ):
            active_model = request.app.state.social_brain.model

        return JSONResponse({"config": masked_config, "active_model": active_model})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def save_social_config(request: Request) -> JSONResponse:
    """Save the social configuration."""
    try:
        data = await request.json()
        incoming_config = data.get("config", {})

        from pathlib import Path

        config_path = Path("config/social.json")
        existing_config = {}
        if config_path.exists():
            with open(config_path, "r") as f:
                existing_config = json.load(f)

        # Merge incoming into existing (handling masks)
        _merge_social_config(existing_config, incoming_config)

        with open(config_path, "w") as f:
            json.dump(existing_config, f, indent=4)

        # Dynamic reload of model if available
        if (
            hasattr(request.app.state, "social_brain")
            and request.app.state.social_brain
        ):
            new_model = existing_config.get("model")
            request.app.state.social_brain.update_model(new_model)

        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
