from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from suzent.core.providers.catalog import PROVIDER_ENV_KEYS
from suzent.logger import get_logger

logger = get_logger(__name__)


def resolve_api_key(
    provider: str, config: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """Resolve the API key for a provider.

    Checks (in order):
    1. Explicit ``config["api_key"]`` or ``config[ENV_KEY]``
    2. SecretManager (keyring / encrypted DB)
    3. Environment variables (fallback)
    """
    env_keys = PROVIDER_ENV_KEYS.get(provider, [f"{provider.upper()}_API_KEY"])

    # 1. Check explicit config dict
    if config:
        val = config.get("api_key")
        if val:
            return val
        for env_key in env_keys:
            val = config.get(env_key)
            if val:
                return val

    # 2. Check SecretManager (handles both backend + env fallback)
    try:
        from suzent.core.secrets import get_secret_manager

        sm = get_secret_manager()
        for env_key in env_keys:
            val = sm.get(env_key)
            if val:
                return val
    except Exception:
        # Fall back to raw env if SecretManager init fails
        pass

    # 3. Raw environment fallback (redundant if SecretManager works, but safe)
    for env_key in env_keys:
        val = os.environ.get(env_key)
        if val:
            return val

    return None


def get_enabled_models_from_db() -> List[str]:
    """Aggregate all enabled/available models from user provider config."""
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
        from suzent.core.providers.catalog import PROVIDER_REGISTRY

        defaults = [m["id"] for p in PROVIDER_REGISTRY for m in p.default_models]
        return sorted(set(defaults))

    from suzent.core.providers.catalog import PROVIDER_REGISTRY

    all_models = [
        model_id
        for p in PROVIDER_REGISTRY
        for model_id in custom_config.get(p.id, {}).get("enabled_models", [])
    ]

    return sorted(set(all_models))


def _load_user_provider_config() -> Dict[str, Any]:
    """Load the user's saved provider config blob from the DB, or {}."""
    import json

    from suzent.database import get_database

    db = get_database()
    api_keys = db.get_api_keys() or {}
    blob = api_keys.get("_PROVIDER_CONFIG_")
    if not blob:
        return {}
    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _provider_is_configured(spec) -> bool:
    """Return True if ``spec`` has usable credentials.

    For standard providers, this means an API key is resolvable. For the
    ChatGPT subscription provider (no env keys, OAuth-based), it means the
    cached access token is still valid.
    """
    if spec.env_keys:
        return resolve_api_key(spec.id) is not None

    if spec.api_type == "chatgpt_subscription":
        # Avoid pulling the ChatGPT provider stack at module import time.
        from suzent.core.providers.factory import ProviderFactory

        try:
            provider = ProviderFactory.get_provider(spec.id, {})
        except Exception as exc:
            logger.debug(
                "ChatGPT provider unavailable while checking default model: {}", exc
            )
            return False
        return bool(getattr(provider, "is_authenticated", lambda: False)())

    return False


def get_default_chat_model() -> Optional[str]:
    """Return the default chat model id from the first configured provider.

    Walks ``PROVIDER_REGISTRY`` in catalog order and returns the first model
    available from a provider that has credentials.

    Semantics must match ``get_enabled_models_from_db`` so the returned id is
    always a member of ``/config.models``:

    * **No ``_PROVIDER_CONFIG_`` blob saved** (fresh install): fall back to the
      provider's catalog ``default_models[0]``.
    * **Blob saved**: the blob is the source of truth. Honor each provider's
      ``enabled_models`` strictly — an explicit empty list, or no entry at
      all, means "this provider exposes no chat models" and we walk on. We do
      *not* fall back to catalog defaults in this case, otherwise the helper
      could return a model that the frontend cannot select.

    Returns ``None`` if no provider is configured.
    """
    from suzent.core.providers.catalog import PROVIDER_REGISTRY

    user_provider_config = _load_user_provider_config()
    blob_present = bool(user_provider_config)

    for spec in PROVIDER_REGISTRY:
        if not _provider_is_configured(spec):
            continue

        if blob_present:
            # Strictly honor the saved blob — matches get_enabled_models_from_db.
            enabled = user_provider_config.get(spec.id, {}).get("enabled_models") or []
            if enabled:
                return enabled[0]
            continue

        # Fresh install: blob absent, fall back to catalog defaults.
        if spec.default_models:
            return spec.default_models[0]["id"]

    return None


def get_effective_memory_config() -> Dict[str, str]:
    """Get effective memory config, preferring user settings over CONFIG defaults."""
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
        logger.warning(f"Failed to fetch memory config, using defaults: {e}")
        embedding_model = CONFIG.embedding_model
        extraction_model = CONFIG.extraction_model

    return {
        "embedding_model": embedding_model,
        "extraction_model": extraction_model,
    }
