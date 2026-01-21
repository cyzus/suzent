"""
Configuration-related API routes.

Handles configuration endpoints that provide frontend-consumable
application settings including user preferences, API keys, and provider management.
"""

import json
import os
import traceback
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


async def get_config(request: Request) -> JSONResponse:
    """Return frontend-consumable configuration merged with user preferences."""
    db = get_database()
    user_prefs = db.get_user_preferences()

    sandbox_enabled = getattr(CONFIG, "sandbox_enabled", False)
    sandbox_volumes = CONFIG.sandbox_volumes or []
    available_models = get_enabled_models_from_db()

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
    }

    if user_prefs:
        data["userPreferences"] = {
            "model": user_prefs.model,
            "agent": user_prefs.agent,
            "tools": user_prefs.tools,
            "memory_enabled": user_prefs.memory_enabled,
            "sandbox_enabled": user_prefs.sandbox_enabled,
            "sandbox_volumes": user_prefs.sandbox_volumes,
        }

    return JSONResponse(data)


async def save_preferences(request: Request) -> JSONResponse:
    """Save user preferences to the database."""
    data = await request.json()

    db = get_database()
    success = db.save_user_preferences(
        model=data.get("model"),
        agent=data.get("agent"),
        tools=data.get("tools"),
        memory_enabled=data.get("memory_enabled"),
        sandbox_enabled=data.get("sandbox_enabled"),
        sandbox_volumes=data.get("sandbox_volumes"),
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
