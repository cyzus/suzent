from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from suzent.core.providers.catalog import PROVIDER_CONFIG, PROVIDER_ENV_KEYS
from suzent.logger import get_logger

logger = get_logger(__name__)


def resolve_api_key(
    provider: str, config: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """Resolve the API key for a provider.

    Checks (in order):
    1. Explicit ``config["api_key"]`` or ``config[ENV_KEY]``
    2. Environment variables from ``PROVIDER_ENV_KEYS``
    3. Falls back to ``<PROVIDER_ID>.upper()_API_KEY``
    """
    env_keys = PROVIDER_ENV_KEYS.get(provider, [f"{provider.upper()}_API_KEY"])

    if config:
        val = config.get("api_key")
        if val:
            return val
        for env_key in env_keys:
            val = config.get(env_key)
            if val:
                return val

    for env_key in env_keys:
        val = os.environ.get(env_key)
        if val:
            return val

    return None


def get_enabled_models_from_db() -> List[str]:
    """Aggregate all enabled/available models from provider config stored in the database."""
    import json
    from suzent.config import CONFIG
    from suzent.database import get_database

    db = get_database()
    api_keys = db.get_api_keys() or {}
    provider_config_blob = api_keys.get("_PROVIDER_CONFIG_")

    custom_config = {}
    if provider_config_blob:
        try:
            custom_config = json.loads(provider_config_blob)
        except json.JSONDecodeError:
            pass

    if not custom_config:
        if CONFIG.model_options:
            return CONFIG.model_options
        defaults = [
            m["id"] for p in PROVIDER_CONFIG for m in p.get("default_models", [])
        ]
        return sorted(set(defaults))

    all_models = [
        model_id
        for p in PROVIDER_CONFIG
        for model_id in custom_config.get(p["id"], {}).get("enabled_models", [])
    ]

    return sorted(set(all_models))


def get_effective_memory_config() -> Dict[str, str]:
    """Get effective memory config, preferring user DB settings over CONFIG defaults."""
    from suzent.config import CONFIG
    from suzent.database import get_database

    try:
        db = get_database()
        memory_config = db.get_memory_config()

        embedding_model = (
            memory_config.embedding_model
            if memory_config and memory_config.embedding_model
            else CONFIG.embedding_model
        )
        extraction_model = (
            memory_config.extraction_model
            if memory_config and memory_config.extraction_model
            else CONFIG.extraction_model
        )
    except Exception as e:
        logger.warning(f"Failed to fetch memory config from DB, using defaults: {e}")
        embedding_model = CONFIG.embedding_model
        extraction_model = CONFIG.extraction_model

    return {
        "embedding_model": embedding_model,
        "extraction_model": extraction_model,
    }
