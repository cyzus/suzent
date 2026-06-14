"""
Configuration-related API routes.

Handles configuration endpoints that provide frontend-consumable
application settings including user preferences, API keys, and provider management.
"""

import json
import os
import traceback
from pathlib import Path
from typing import Any
import asyncio

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.config import CONFIG
from suzent.core.providers import (
    PROVIDER_REGISTRY,
    ProviderFactory,
    get_default_chat_model,
    get_effective_memory_config,
    get_enabled_models_from_db,
    invalidate_default_model_cache,
)
from suzent.tools.registry import get_tool_groups
from suzent.database import get_database
from suzent.core.volume_metadata import refresh_volume_metadata
from suzent.logger import get_logger

logger = get_logger(__name__)


def get_resource_path(path: str) -> Path:
    """Get absolute path to resource, using PROJECT_DIR for bundled/dev mode."""
    from suzent.config import PROJECT_DIR

    return PROJECT_DIR / path


def _schedule_volume_metadata_refresh(volumes: list[str]) -> None:
    """Refresh volume metadata without blocking the request path."""
    if not volumes:
        return

    async def _refresh() -> None:
        try:
            db = get_database()
            await asyncio.to_thread(refresh_volume_metadata, db, volumes)
        except Exception as exc:
            logger.warning("Volume metadata refresh failed: {}", exc)

    try:
        asyncio.create_task(_refresh())
    except RuntimeError:
        try:
            refresh_volume_metadata(get_database(), volumes)
        except Exception as exc:
            logger.warning("Volume metadata refresh failed: {}", exc)


async def get_config(request: Request) -> JSONResponse:
    """Return frontend-consumable configuration merged with user preferences."""
    db = get_database()
    user_prefs = db.get_user_preferences()

    sandbox_enabled = getattr(CONFIG, "sandbox_enabled", False)
    sandbox_volumes = CONFIG.sandbox_volumes or []
    available_models = get_enabled_models_from_db()
    default_model = get_default_chat_model()

    mem_config = get_effective_memory_config()
    embedding_model = mem_config["embedding_model"]
    extraction_model = mem_config["extraction_model"]

    data: dict[str, Any] = {
        "title": CONFIG.title,
        "models": available_models,
        "defaultModel": default_model,
        "agents": CONFIG.agent_options,
        "tools": [t for t in CONFIG.tool_options if t != "SkillTool"],
        "toolGroups": get_tool_groups(),
        "defaultTools": [t for t in CONFIG.default_tools if t != "SkillTool"],
        "codeTag": CONFIG.code_tag,
        "userId": CONFIG.user_id,
        "globalSandboxVolumes": sandbox_volumes,
        "sandboxEnabled": sandbox_enabled,
        "maxContextTokens": CONFIG.max_context_tokens,
        "embeddingModel": CONFIG.embedding_model,
        "extractionModel": CONFIG.extraction_model,
        "volumeMetadata": db.get_volume_metadata(sandbox_volumes),
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
        if user_prefs.sandbox_volumes:
            data["userPreferences"]["volume_metadata"] = db.get_volume_metadata(
                user_prefs.sandbox_volumes
            )
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
    if success and data.get("sandbox_volumes") is not None:
        _schedule_volume_metadata_refresh(data.get("sandbox_volumes") or [])

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


def _get_default_config_path() -> Path:
    from suzent.config import PROJECT_DIR

    return PROJECT_DIR / "config" / "default.yaml"


def _load_default_config_file() -> dict[str, Any]:
    path = _get_default_config_path()
    if not path.exists():
        return {}

    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "PyYAML is required to update global sandbox mounts"
        ) from exc

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ValueError("config/default.yaml must contain a mapping at the root")
    return data


def _save_default_config_file(config_data: dict[str, Any]) -> None:
    path = _get_default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "PyYAML is required to update global sandbox mounts"
        ) from exc

    with path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(config_data, file, sort_keys=False, allow_unicode=False)


def _load_local_config_file() -> dict[str, Any]:
    from suzent.core.user_config import get_local_config_path

    path = get_local_config_path()
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "PyYAML is required to update global sandbox mounts"
        ) from exc
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError("config/local.yaml must contain a mapping at the root")
    return data


def _save_local_config_file(config_data: dict[str, Any]) -> None:
    from suzent.core.user_config import get_local_config_path

    path = get_local_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "PyYAML is required to update global sandbox mounts"
        ) from exc
    with path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(config_data, file, sort_keys=False, allow_unicode=False)


def _normalize_sandbox_volumes(raw_volumes: Any) -> list[str]:
    if not isinstance(raw_volumes, list):
        raise ValueError("sandbox_volumes must be an array of strings")

    normalized: list[str] = []
    seen: set[str] = set()
    for volume in raw_volumes:
        if not isinstance(volume, str):
            raise ValueError("sandbox_volumes must contain only strings")

        cleaned = volume.strip()
        if not cleaned or cleaned in seen:
            continue

        normalized.append(cleaned)
        seen.add(cleaned)

    return normalized


async def save_global_sandbox_config(request: Request) -> JSONResponse:
    """Persist global sandbox settings to the machine-local config file.

    sandbox_volumes are machine-specific (host paths differ per device) and must
    live in ~/.suzent/config/local.yaml, which the loader merges LAST and which is
    never synced across devices. Writing them to default.yaml would be silently
    overridden by local.yaml on the next restart.
    """
    try:
        payload = await request.json()
        sandbox_volumes = _normalize_sandbox_volumes(payload.get("sandbox_volumes", []))

        config_data = _load_local_config_file()
        config_data["sandbox_volumes"] = sandbox_volumes
        _save_local_config_file(config_data)

        # Keep runtime config in sync without requiring restart.
        CONFIG.sandbox_volumes = sandbox_volumes
        db = get_database()
        _schedule_volume_metadata_refresh(sandbox_volumes)

        return JSONResponse(
            {
                "success": True,
                "globalSandboxVolumes": sandbox_volumes,
                "volumeMetadata": db.get_volume_metadata(sandbox_volumes),
            }
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


async def get_api_keys_status(request: Request) -> JSONResponse:
    """Get configured providers and their status with masked secrets."""
    try:
        from suzent.core.secrets import get_secret_manager

        sm = get_secret_manager()

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
        for spec in PROVIDER_REGISTRY:
            provider_id = spec.id
            user_conf = custom_config.get(provider_id, {})

            provider_data: dict[str, Any] = {
                "id": provider_id,
                "label": spec.label,
                "logo_url": spec.logo_url,
                "default_models": spec.default_models,
                "user_defined": spec.user_defined,
                "fields": [],
                "models": [],
            }

            for field in spec.fields:
                key = field["key"]
                # Use SecretManager to check all sources
                val = sm.get(key)
                source = sm.get_source(key)

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
                            display_val = (
                                f"{val[:4]}...{val[-4:]}" if len(val) >= 8 else "••••"
                            )
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
                        "source": source,
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
    """Save API keys via SecretManager and inject into runtime environment."""
    try:
        from suzent.core.secrets import get_secret_manager

        sm = get_secret_manager()

        data = await request.json()
        keys = data.get("keys", {})

        db = get_database()
        count = 0

        # Track which provider field keys are being set/cleared
        newly_set_keys: set[str] = set()
        cleared_keys: set[str] = set()

        for key, value in keys.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue

            # Skip masked values that weren't changed
            if "..." in value and "(env)" in value:
                continue

            if key == "_PROVIDER_CONFIG_":
                # Handled below after processing all plain keys
                continue

            if not value:
                sm.delete(key)
                cleared_keys.add(key)
            else:
                sm.set(key, value)
                newly_set_keys.add(key)
                count += 1

        # Process _PROVIDER_CONFIG_ with auto-population of default_models
        provider_config_blob = keys.get("_PROVIDER_CONFIG_")
        if isinstance(provider_config_blob, str) and provider_config_blob:
            try:
                custom_config: dict[str, Any] = json.loads(provider_config_blob)
            except json.JSONDecodeError:
                custom_config = {}

            # Build a map of provider field keys → provider id
            key_to_provider: dict[str, str] = {}
            provider_defaults: dict[str, list[str]] = {}
            for p in PROVIDER_REGISTRY:
                pid = p.id
                provider_defaults[pid] = [m["id"] for m in p.default_models]
                for field in p.fields:
                    key_to_provider[field["key"]] = pid

            # For each provider whose key was newly set and has no enabled_models,
            # auto-populate with default_models so the UI shows options immediately.
            for env_key in newly_set_keys:
                pid = key_to_provider.get(env_key)
                if pid and not custom_config.get(pid, {}).get("enabled_models"):
                    defaults = provider_defaults.get(pid, [])
                    if defaults:
                        if pid not in custom_config:
                            custom_config[pid] = {}
                        custom_config[pid]["enabled_models"] = defaults

            updated_blob = json.dumps(custom_config)
            db.save_api_key("_PROVIDER_CONFIG_", updated_blob)
            os.environ["_PROVIDER_CONFIG_"] = updated_blob
            count += 1
            invalidate_default_model_cache()

        return JSONResponse({"success": True, "updated": count})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def verify_provider(request: Request) -> JSONResponse:
    """Verify provider credentials and fetch available models."""
    try:
        provider_id = request.path_params["provider_id"]
        data = await request.json()
        config = data.get("config", {})

        if provider_id == "chatgpt":
            from suzent.core.providers.chatgpt import ChatGPTProvider

            provider = ChatGPTProvider("chatgpt", config)
            connected = await asyncio.to_thread(provider.is_authenticated)
            if not connected:
                return JSONResponse(
                    {
                        "success": False,
                        "models": [],
                        "message": "Not signed in. Use Settings → ChatGPT Subscription to sign in.",
                    }
                )
            models = await provider.list_models()
            if models:
                from suzent.core.model_registry import (
                    save_discovered_models,
                    get_model_registry,
                )

                save_discovered_models("chatgpt", [m.id for m in models])
                get_model_registry().reload()
            return JSONResponse(
                {
                    "success": True,
                    "models": [m.model_dump() for m in models],
                }
            )

        try:
            provider = ProviderFactory.get_provider(provider_id, config)
        except ValueError:
            return JSONResponse(
                {"error": f"Provider {provider_id} not supported"},
                status_code=400,
            )

        models = await provider.list_models()

        if models:
            from suzent.core.model_registry import (
                save_discovered_models,
                get_model_registry,
            )

            save_discovered_models(provider_id, [m.id for m in models])
            get_model_registry().reload()

        return JSONResponse(
            {
                "success": len(models) > 0,
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
        from suzent.config import PROJECT_DIR

        # Use PROJECT_DIR for correct path in frozen mode
        config_path = PROJECT_DIR / "config" / "social.json"
        if not config_path.exists():
            return JSONResponse({"config": {}})

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

        from suzent.config import PROJECT_DIR

        config_path = PROJECT_DIR / "config" / "social.json"
        existing_config = {}
        if config_path.exists():
            with open(config_path, "r") as f:
                existing_config = json.load(f)

        # Merge incoming into existing (handling masks)
        _merge_social_config(existing_config, incoming_config)

        with open(config_path, "w") as f:
            json.dump(existing_config, f, indent=4)

        from suzent.server import reload_social

        asyncio.create_task(reload_social(request.app, existing_config))

        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Cost Tracking Endpoints
# ---------------------------------------------------------------------------


async def get_global_cost(request: Request) -> JSONResponse:
    """GET /api/config/cost/global?days=30 — global cost overview."""
    try:
        from suzent.core.cost_tracker import get_cost_tracker

        days = int(request.query_params.get("days", "30"))
        tracker = get_cost_tracker()
        data = await tracker.get_global_cost(days=days)
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_chat_cost(request: Request) -> JSONResponse:
    """GET /api/config/cost/chat/{chat_id} — single chat cost."""
    try:
        from suzent.core.cost_tracker import get_cost_tracker

        chat_id = request.path_params["chat_id"]
        tracker = get_cost_tracker()
        data = await tracker.get_chat_cost(chat_id)
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_daily_cost(request: Request) -> JSONResponse:
    """GET /api/config/cost/daily?days=30 — daily cost breakdown."""
    try:
        from suzent.core.cost_tracker import get_cost_tracker

        days = int(request.query_params.get("days", "30"))
        tracker = get_cost_tracker()
        data = await tracker.get_daily_breakdown(days=days)
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_hourly_cost(request: Request) -> JSONResponse:
    """GET /api/config/cost/hourly?days=30 — hourly cost breakdown."""
    try:
        from suzent.core.cost_tracker import get_cost_tracker

        days = int(request.query_params.get("days", "30"))
        tracker = get_cost_tracker()
        data = await tracker.get_hourly_breakdown(days=days)
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_activity_grid(request: Request) -> JSONResponse:
    """GET /api/config/cost/activity-grid?range=1|7|30|all — dynamic activity grid."""
    try:
        from suzent.core.cost_tracker import get_cost_tracker

        rng = request.query_params.get("range", "30")
        tracker = get_cost_tracker()

        if rng == "1":
            data = await tracker.get_activity_binned(days=1, interval_minutes=4)
        elif rng == "7":
            data = await tracker.get_activity_binned(days=7, interval_minutes=30)
        elif rng == "30":
            data = await tracker.get_activity_binned(days=30, interval_minutes=120)
        else:
            data = await tracker.get_activity_binned(days=365, interval_minutes=1440)

        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_models_cost(request: Request) -> JSONResponse:
    """GET /api/config/cost/models?days=30 — model cost breakdown."""
    try:
        from suzent.core.cost_tracker import get_cost_tracker

        days = int(request.query_params.get("days", "30"))
        tracker = get_cost_tracker()
        data = await tracker.get_model_breakdown(days=days)
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def get_activity_cost(request: Request) -> JSONResponse:
    """GET /api/config/cost/activity — activity statistics (streaks, peak, etc)."""
    try:
        from suzent.core.cost_tracker import get_cost_tracker

        tracker = get_cost_tracker()
        data = await tracker.get_activity_stats()
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Role Model Endpoints
# ---------------------------------------------------------------------------


async def get_role_models(request: Request) -> JSONResponse:
    """GET /api/config/role-models — get current role→model mappings."""
    try:
        from suzent.core.role_router import get_role_router

        router = get_role_router()
        return JSONResponse({"roles": router.list_roles()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def save_role_models(request: Request) -> JSONResponse:
    """POST /api/config/role-models — save role→model mappings."""
    try:
        from suzent.core.role_router import get_role_router

        data = await request.json()
        roles = data.get("roles", {})

        router = get_role_router()
        router.load_from_dict(roles)
        router.save_to_db()

        return JSONResponse({"success": True, "roles": router.list_roles()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Role Suggestions Endpoint
# ---------------------------------------------------------------------------


async def get_role_suggestions(request: Request) -> JSONResponse:
    """GET /api/config/role-suggestions — mode-filtered model suggestions per role.

    Returns a dict mapping each role to a list of suitable model IDs drawn
    from the enabled provider models (chat roles) and the model capabilities
    registry (embedding / tts / image_generation roles).
    """
    try:
        from suzent.core.model_registry import get_model_registry
        from suzent.core.providers.helpers import get_enabled_models_from_db

        registry = get_model_registry()
        chat_models = get_enabled_models_from_db()

        # Vision: only enabled models with confirmed supports_vision=True
        vision_models = [m for m in chat_models if registry.supports_vision(m)]

        # Specialised modes from capabilities file
        caps = registry._capabilities  # type: ignore[attr-defined]
        embedding_models = sorted(m for m, c in caps.items() if c.mode == "embedding")
        image_gen_models = sorted(
            m for m, c in caps.items() if c.mode == "image_generation"
        )
        tts_models = sorted(m for m, c in caps.items() if c.mode == "tts")

        return JSONResponse(
            {
                "primary": chat_models,
                "cheap": chat_models,
                "vision": vision_models,
                "embedding": embedding_models,
                "image_generation": image_gen_models,
                "tts": tts_models,
            }
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Custom Provider Endpoint
# ---------------------------------------------------------------------------


async def save_custom_provider(request: Request) -> JSONResponse:
    """POST /api/config/providers/custom — add a user-defined provider."""
    try:
        import json as _json
        from suzent.core.providers.catalog import _CONFIG_DIR, reload_registry

        data = await request.json()

        # Validate required fields
        for field in ("id", "label", "api_type"):
            if field not in data:
                return JSONResponse(
                    {"error": f"Missing required field: {field}"}, status_code=400
                )

        user_path = _CONFIG_DIR / "providers.user.json"

        # Load existing user providers
        existing: list = []
        if user_path.exists():
            try:
                raw = _json.loads(user_path.read_text(encoding="utf-8"))
                existing = raw.get("providers", [])
            except _json.JSONDecodeError:
                pass

        # Check for duplicate ID
        if any(p.get("id") == data["id"] for p in existing):
            return JSONResponse(
                {"error": f"Provider '{data['id']}' already exists"}, status_code=409
            )

        existing.append(data)
        user_path.write_text(
            _json.dumps({"providers": existing}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Hot-reload
        reload_registry()

        return JSONResponse({"success": True, "provider_id": data["id"]})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def sync_capabilities(request: Request) -> JSONResponse:
    """POST /api/config/capabilities/sync — pull LiteLLM capability data."""
    try:
        from suzent.core.model_registry import sync_from_litellm, get_model_registry

        stats = await sync_from_litellm()
        get_model_registry().reload()

        total = sum(stats.values())
        return JSONResponse(
            {"success": True, "providers": len(stats), "models": total, "detail": stats}
        )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


async def delete_custom_provider(request: Request) -> JSONResponse:
    """DELETE /api/config/providers/custom/{provider_id} — remove a user-defined provider."""
    try:
        import json as _json
        from suzent.core.providers.catalog import _CONFIG_DIR, reload_registry

        provider_id = request.path_params["provider_id"]

        user_path = _CONFIG_DIR / "providers.user.json"
        if not user_path.exists():
            return JSONResponse(
                {"error": "No custom providers configured"}, status_code=404
            )

        raw = _json.loads(user_path.read_text(encoding="utf-8"))
        providers = raw.get("providers", [])
        filtered = [p for p in providers if p.get("id") != provider_id]

        if len(filtered) == len(providers):
            return JSONResponse(
                {"error": f"Provider '{provider_id}' not found"}, status_code=404
            )

        user_path.write_text(
            _json.dumps({"providers": filtered}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        reload_registry()

        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
