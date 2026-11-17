from __future__ import annotations

import json
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


def _load_user_provider_config() -> Optional[Dict[str, Any]]:
    """Return the parsed _PROVIDER_CONFIG_ blob, or None if absent/invalid.

    None means no blob has ever been saved (fresh install).
    {} means an empty blob was explicitly saved.
    """
    from suzent.database import get_database

    blob = (get_database().get_api_keys() or {}).get("_PROVIDER_CONFIG_")
    if blob is None:
        return None
    try:
        parsed = json.loads(blob)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _normalize_provider_model_id(provider_id: str, model_id: str) -> Optional[str]:
    """Ensure a model ID belonging to ``provider_id`` carries its ``provider_id/`` prefix.

    Drops bare entries that merely repeat the provider ID itself (e.g. ``"Gemini"``
    inside ``gemini``).
    """
    if not isinstance(model_id, str):
        return None
    trimmed = model_id.strip()
    if not trimmed:
        return None
    if "/" not in trimmed:
        if trimmed.lower() == provider_id.lower():
            return None
        return f"{provider_id}/{trimmed}"
    return trimmed


def _provider_models(spec, custom_config: Optional[Dict[str, Any]]) -> List[str]:
    """Return available chat models for a single provider spec.

    * If ``custom_config`` is present and explicitly defines a ``disabled_models``
      set, those IDs are excluded.
    * If ``custom_config`` has a non-empty ``enabled_models`` list, include them.
    * When a provider has valid credentials (``_provider_is_configured(spec)``)
      and was not explicitly cleared to ``enabled_models == []`` (unless no
      ``enabled_models`` key was set or auto-discovery is active), also include
      models discovered/shipped in the capability registry and ``default_models``
      plus ``custom_models`` so configured providers work immediately without a
      manual check-box step.
    """
    from suzent.core.model_registry import list_provider_chat_models

    if custom_config is None:
        if not _provider_is_configured(spec):
            return []
        models = [m["id"] for m in spec.default_models]
        models.extend(list_provider_chat_models(spec.id))
        return list(dict.fromkeys(models))

    entry = custom_config.get(spec.id)
    if isinstance(entry, dict) and entry.get("enabled") is False:
        return []

    disabled = {
        norm
        for m in (
            (entry or {}).get("disabled_models", []) if isinstance(entry, dict) else []
        )
        if (norm := _normalize_provider_model_id(spec.id, m)) is not None
    }
    custom_models = [
        norm
        for m in (
            list(entry.get("custom_models") or []) if isinstance(entry, dict) else []
        )
        if (norm := _normalize_provider_model_id(spec.id, m)) is not None
    ]

    # Explicit empty enabled_models list in saved config (without starred_models)
    # means the provider's chat models were explicitly cleared. When the user
    # unstars all models in the UI, starred_models == [] is present and the
    # provider still exposes its auto-discovered / catalog models.
    if isinstance(entry, dict) and "enabled_models" in entry:
        explicit_enabled = [
            norm
            for m in list(entry.get("enabled_models") or [])
            if (norm := _normalize_provider_model_id(spec.id, m)) is not None
        ]
        if not explicit_enabled and not custom_models and "starred_models" not in entry:
            return []
    else:
        explicit_enabled = []

    models: List[str] = []
    for m in explicit_enabled:
        if m not in disabled:
            models.append(m)
    for m in custom_models:
        if m not in disabled and m not in models:
            models.append(m)

    # For configured providers (excluding keyless local endpoints that were not
    # explicitly enabled), also surface discovered/shipped chat models and catalog
    # defaults so newly verified or env-configured providers appear automatically.
    is_configured = _provider_is_configured(spec)
    if is_configured and (
        not spec.api_key_optional or explicit_enabled or custom_models
    ):
        for m in spec.default_models:
            mid = m["id"]
            if mid not in disabled and mid not in models:
                models.append(mid)
        for mid in list_provider_chat_models(spec.id):
            if mid not in disabled and mid not in models:
                models.append(mid)

    return models


def get_enabled_models_from_db() -> List[str]:
    """Aggregate all enabled/available models from user provider config and configured providers."""
    from suzent.config import CONFIG

    custom_config = _load_user_provider_config()

    if custom_config is None:
        if CONFIG.model_options:
            return CONFIG.model_options
        from suzent.core.providers.catalog import PROVIDER_REGISTRY

        configured_models: List[str] = []
        for p in PROVIDER_REGISTRY:
            configured_models.extend(_provider_models(p, None))
        if configured_models:
            return sorted(set(configured_models))

        defaults = [m["id"] for p in PROVIDER_REGISTRY for m in p.default_models]
        return sorted(set(defaults))

    from suzent.core.providers.catalog import PROVIDER_REGISTRY

    all_models: List[str] = []
    for p in PROVIDER_REGISTRY:
        all_models.extend(_provider_models(p, custom_config))

    return sorted(set(all_models))


def get_starred_models_from_db() -> List[str]:
    """Return user-starred (favorite) model IDs from ``_PROVIDER_CONFIG_``.

    Reads ``starred_models`` per provider when present so legacy
    ``enabled_models`` blobs (which previously stored every discovered model)
    do not flood the Starred list.
    """
    custom_config = _load_user_provider_config()
    if not custom_config:
        return []

    from suzent.core.providers.catalog import PROVIDER_REGISTRY

    starred: List[str] = []
    for p in PROVIDER_REGISTRY:
        entry = custom_config.get(p.id)
        if not isinstance(entry, dict) or entry.get("enabled") is False:
            continue
        raw_list = entry.get("starred_models") if "starred_models" in entry else []
        for m in list(raw_list or []):
            norm = _normalize_provider_model_id(p.id, m)
            if norm and norm not in starred:
                starred.append(norm)
    return starred


def _provider_is_configured(spec) -> bool:
    """Return True if the provider has usable credentials or allows keyless access."""
    if spec.api_key_optional:
        return True
    if spec.env_keys:
        return resolve_api_key(spec.id) is not None
    if spec.api_type == "chatgpt_subscription":
        from suzent.core.providers.factory import ProviderFactory

        try:
            provider = ProviderFactory.get_provider(spec.id, {})
        except Exception as exc:
            logger.debug(
                "ChatGPT provider unavailable while checking default model: {}", exc
            )
            return False
        try:
            # /config is part of desktop startup. Never perform an OAuth refresh
            # (and therefore a network request) while choosing its default model.
            return bool(provider.is_authenticated(refresh=False))
        except Exception as exc:
            logger.warning(
                "ChatGPT credentials could not be checked while choosing the "
                "default model: {}",
                exc,
            )
            return False
    return False


def get_configured_provider_ids() -> set[str]:
    """Provider IDs/aliases eligible for recommendations; no credential verification calls."""
    from suzent.core.providers.catalog import PROVIDER_REGISTRY

    config = _load_user_provider_config() or {}
    available: set[str] = set()
    for spec in PROVIDER_REGISTRY:
        entry = config.get(spec.id, {})
        if entry.get("enabled") is False:
            continue
        # Keyless endpoints should not appear just because they ship in the catalog.
        if spec.api_key_optional and not entry.get("enabled_models"):
            continue
        if _provider_is_configured(spec):
            available.update([spec.id, *spec.aliases])
    return available


_UNSET = object()
_default_model_cache: Any = _UNSET


def invalidate_default_model_cache() -> None:
    """Invalidate the cached default model (call after provider config changes)."""
    global _default_model_cache
    _default_model_cache = _UNSET


def _compute_default_chat_model() -> Optional[str]:
    """Walks ``PROVIDER_REGISTRY`` in catalog order and returns the first model
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
    blob_present = user_provider_config is not None

    for spec in PROVIDER_REGISTRY:
        if not _provider_is_configured(spec):
            continue

        if blob_present:
            entry = user_provider_config.get(spec.id)
            if isinstance(entry, dict):
                enabled = entry.get("enabled_models") or []
                if enabled:
                    return enabled[0]
                if "starred_models" in entry and entry.get("enabled") is not False:
                    models = _provider_models(spec, user_provider_config)
                    if models:
                        return models[0]
            continue

        # Fresh install: blob absent, fall back to catalog defaults.
        if spec.default_models:
            return spec.default_models[0]["id"]

    return None


def get_default_chat_model() -> Optional[str]:
    """First model from the first configured provider, in catalog order.

    Cached; call ``invalidate_default_model_cache`` after provider config changes.
    Returns ``None`` when no provider has credentials.
    """
    global _default_model_cache
    if _default_model_cache is _UNSET:
        _default_model_cache = _compute_default_chat_model()
    return _default_model_cache  # type: ignore[return-value]


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
