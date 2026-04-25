"""
Provider catalog — data-driven provider registry.

Loads provider definitions from ``config/providers.json`` (repo-tracked defaults)
and ``config/providers.user.json`` (user-defined overrides, git-ignored).
At runtime these are merged into ``PROVIDER_REGISTRY`` / ``PROVIDER_REGISTRY_BY_ID``.

Legacy constants (``PROVIDER_CONFIG``, ``PROVIDER_ENV_KEYS``,
``OPENAI_COMPAT_PROVIDERS``) are derived from the registry for backward
compatibility; new code should use ``PROVIDER_REGISTRY_BY_ID`` directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

# Root of the project (two levels up from this file → src/suzent/core/providers/)
_PROJECT_DIR = Path(__file__).resolve().parents[4]
_CONFIG_DIR = _PROJECT_DIR / "config"


# ---------------------------------------------------------------------------
# ProviderSpec — the canonical runtime representation of a provider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderSpec:
    """Immutable description of a model provider loaded from JSON."""

    id: str
    label: str
    api_type: str  # "openai" | "anthropic" | "google" | "xai" | "openrouter" | "ollama" | "litellm_proxy" | "bedrock"
    env_keys: list[str] = field(default_factory=list)
    fields: list[dict[str, Any]] = field(default_factory=list)
    default_models: list[dict[str, str]] = field(default_factory=list)
    base_url: Optional[str] = None
    native_provider: Optional[dict[str, str]] = (
        None  # {"module": "...", "class": "..."}
    )
    aliases: list[str] = field(default_factory=list)
    model_settings: Optional[dict[str, Any]] = None  # pydantic-ai ModelSettings kwargs
    logo_url: Optional[str] = None
    user_defined: bool = False

    @property
    def is_compat(self) -> bool:
        """True if this provider uses a custom base_url (compat mode)."""
        return self.base_url is not None

    @property
    def has_native_provider(self) -> bool:
        """True if a pydantic-ai native provider class is specified."""
        return self.native_provider is not None


# ---------------------------------------------------------------------------
# Loader — reads & merges JSON files
# ---------------------------------------------------------------------------


def _parse_provider(raw: dict[str, Any], *, user_defined: bool = False) -> ProviderSpec:
    """Create a ProviderSpec from a raw JSON dict."""
    return ProviderSpec(
        id=raw["id"],
        label=raw["label"],
        api_type=raw["api_type"],
        env_keys=raw.get("env_keys", []),
        fields=raw.get("fields", []),
        default_models=raw.get("default_models", []),
        base_url=raw.get("base_url"),
        native_provider=raw.get("native_provider"),
        aliases=raw.get("aliases", []),
        model_settings=raw.get("model_settings"),
        logo_url=raw.get("logo_url"),
        user_defined=user_defined,
    )


def _load_json_file(path: Path) -> list[dict[str, Any]]:
    """Load the ``providers`` array from a JSON file, or [] if missing."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("providers", [])
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Failed to load provider JSON {}: {}", path, exc)
        return []


def load_provider_registry() -> list[ProviderSpec]:
    """Load and merge base + user provider definitions."""
    base_entries = _load_json_file(_CONFIG_DIR / "providers.json")
    user_entries = _load_json_file(_CONFIG_DIR / "providers.user.json")

    specs: list[ProviderSpec] = [_parse_provider(e) for e in base_entries]
    specs.extend(_parse_provider(e, user_defined=True) for e in user_entries)
    return specs


# ---------------------------------------------------------------------------
# Module-level singletons (populated at import time)
# ---------------------------------------------------------------------------

PROVIDER_REGISTRY: list[ProviderSpec] = load_provider_registry()

PROVIDER_REGISTRY_BY_ID: Dict[str, ProviderSpec] = {}
for _spec in PROVIDER_REGISTRY:
    PROVIDER_REGISTRY_BY_ID[_spec.id] = _spec
    for _alias in _spec.aliases:
        PROVIDER_REGISTRY_BY_ID[_alias] = _spec


def reload_registry() -> None:
    """Hot-reload provider registry (e.g. after user adds a custom provider)."""
    global PROVIDER_REGISTRY
    PROVIDER_REGISTRY = load_provider_registry()
    PROVIDER_REGISTRY_BY_ID.clear()
    for spec in PROVIDER_REGISTRY:
        PROVIDER_REGISTRY_BY_ID[spec.id] = spec
        for alias in spec.aliases:
            PROVIDER_REGISTRY_BY_ID[alias] = spec


# ---------------------------------------------------------------------------
# Legacy compatibility aliases — derived from the registry
# ---------------------------------------------------------------------------

# PROVIDER_CONFIG: the old list-of-dicts format consumed by config_routes and helpers
PROVIDER_CONFIG: List[dict] = [
    {
        "id": s.id,
        "label": s.label,
        "logo_url": s.logo_url,
        "default_models": s.default_models,
        "fields": s.fields,
    }
    for s in PROVIDER_REGISTRY
    if not s.user_defined  # legacy constant only contained built-in providers
]

# PROVIDER_CONFIG_BY_ID: O(1) lookup of legacy dicts
PROVIDER_CONFIG_BY_ID: Dict[str, dict] = {
    entry["id"]: entry for entry in PROVIDER_CONFIG
}

# PROVIDER_ENV_KEYS: provider id → env var names
PROVIDER_ENV_KEYS: Dict[str, List[str]] = {s.id: s.env_keys for s in PROVIDER_REGISTRY}
# Also register aliases
for _spec in PROVIDER_REGISTRY:
    for _alias in _spec.aliases:
        if _alias not in PROVIDER_ENV_KEYS:
            PROVIDER_ENV_KEYS[_alias] = _spec.env_keys

# OPENAI_COMPAT_PROVIDERS: provider id → base_url (only compat providers)
OPENAI_COMPAT_PROVIDERS: Dict[str, str] = {
    s.id: s.base_url for s in PROVIDER_REGISTRY if s.base_url is not None
}
# Include aliases for compat providers
for _spec in PROVIDER_REGISTRY:
    if _spec.base_url is not None:
        for _alias in _spec.aliases:
            if _alias not in OPENAI_COMPAT_PROVIDERS:
                OPENAI_COMPAT_PROVIDERS[_alias] = _spec.base_url
