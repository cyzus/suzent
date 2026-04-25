"""
Role-based model router.

Maps logical roles (primary, cheap, vision, tts, embedding, image_generation)
to configured model IDs.  Supports:
  - Per-role model lists with automatic ``FallbackModel`` wrapping
  - DB-persisted role assignments (from frontend Settings)
  - Config YAML defaults
  - Programmatic override via ``set_role()``

Usage::

    router = get_role_router()
    model = router.resolve("primary")      # pydantic-ai Model object
    model_id = router.get_model_id("cheap")  # just the string ID
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Dict, List, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)


class ModelRole(StrEnum):
    """Well-known model roles."""

    PRIMARY = "primary"
    CHEAP = "cheap"
    VISION = "vision"
    TTS = "tts"
    EMBEDDING = "embedding"
    IMAGE_GENERATION = "image_generation"


class RoleConfig:
    """Configuration for a single role's model list."""

    def __init__(self, model_ids: list[str]) -> None:
        self.model_ids = model_ids

    @property
    def primary_model_id(self) -> str | None:
        """First (highest-priority) model ID, or None if empty."""
        return self.model_ids[0] if self.model_ids else None


# Shallow fallback chain: if a role has no explicit config, try these in order.
# TTS / embedding / image_generation intentionally have NO fallback —
# those require specialist models, not a chat model.
_ROLE_FALLBACKS: Dict[str, List[str]] = {
    ModelRole.CHEAP: [ModelRole.PRIMARY],
    ModelRole.VISION: [ModelRole.PRIMARY],
}


# Capability predicate applied when selecting fallback candidates.
# Only models passing this check are returned from the fallback role.
# If a role has no entry here, all fallback candidates are accepted.
def _vision_capable(model_id: str) -> bool:
    try:
        from suzent.core.model_registry import get_model_registry

        return get_model_registry().supports_vision(model_id)
    except Exception:
        return False


_ROLE_CAPABILITY_FILTER: Dict[str, Any] = {
    ModelRole.VISION: _vision_capable,
}


class RoleRouter:
    """Central role → model mapping with fallback support."""

    def __init__(self) -> None:
        self._roles: Dict[str, RoleConfig] = {}

    def set_role(self, role: str, model_ids: list[str]) -> None:
        """Set or overwrite the model list for a role."""
        self._roles[role] = RoleConfig(model_ids)
        logger.debug("Role '{}' → {}", role, model_ids)

    def get_model_id(self, role: str) -> str | None:
        """Get the primary model ID for a role, with shallow fallback.

        Returns the first configured model in the role's list. If the role has
        no explicit config, falls back to the first allowed model from the
        fallback role (e.g. cheap → primary; vision → primary, filtered by
        supports_vision).
        """
        ids = self.get_model_ids(role)
        return ids[0] if ids else None

    def get_model_ids(self, role: str) -> list[str]:
        """Get all model IDs for a role, with shallow fallback.

        Capability filters are applied to fallback candidates only;
        explicitly configured models are returned as-is.
        """
        cfg = self._roles.get(role)
        if cfg and cfg.model_ids:
            return list(cfg.model_ids)

        cap_filter = _ROLE_CAPABILITY_FILTER.get(role)
        for fallback_role in _ROLE_FALLBACKS.get(role, []):
            candidates = self.get_model_ids(fallback_role)
            if cap_filter:
                candidates = [m for m in candidates if cap_filter(m)]
            if candidates:
                logger.debug(
                    "Role '{}' not configured — using {} model(s) from '{}' as fallback",
                    role,
                    len(candidates),
                    fallback_role,
                )
                return candidates
        return []

    def resolve(self, role: str) -> object:
        """Create a pydantic-ai Model (or FallbackModel) for a role.

        Raises ``ValueError`` if the role has no models configured (after fallback).
        """
        from suzent.core.model_factory import create_fallback_model

        model_ids = self.get_model_ids(role)
        if not model_ids:
            raise ValueError(
                f"No models configured for role '{role}'. "
                f"Configure it in Settings → Model Roles."
            )
        return create_fallback_model(model_ids)

    def has_role(self, role: str) -> bool:
        """Check if a role has explicitly configured models (ignores fallback)."""
        cfg = self._roles.get(role)
        return cfg is not None and len(cfg.model_ids) > 0

    def list_roles(self) -> Dict[str, list[str]]:
        """Return all configured roles and their model ID lists."""
        return {role: list(cfg.model_ids) for role, cfg in self._roles.items()}

    def load_from_dict(self, role_models: Dict[str, Any]) -> None:
        """Load role assignments from a dict (e.g. from config YAML or DB).

        Expected format::

            {
                "primary": {"models": ["openai/gpt-4.1", "anthropic/claude-sonnet-4-6"]},
                "cheap": {"models": ["openai/gpt-4.1-mini"]},
                ...
            }

        Or simplified::

            {
                "primary": ["openai/gpt-4.1"],
                "cheap": ["openai/gpt-4.1-mini"],
            }
        """
        for role, value in role_models.items():
            if isinstance(value, dict):
                model_ids = value.get("models", [])
            elif isinstance(value, list):
                model_ids = value
            else:
                logger.warning("Invalid role config for '{}': {}", role, value)
                continue

            if model_ids:
                self.set_role(role, model_ids)

    def load_from_db(self) -> None:
        """Load role assignments from the database."""
        try:
            from suzent.database import get_database

            db = get_database()
            api_keys = db.get_api_keys() or {}
            blob = api_keys.get("_ROLE_MODELS_")
            if blob:
                data = json.loads(blob)
                self.load_from_dict(data)
                logger.info("Loaded {} role mappings from DB", len(data))
        except Exception as e:
            logger.warning("Failed to load role mappings from DB: {}", e)

    def save_to_db(self) -> None:
        """Persist current role assignments to the database."""
        try:
            from suzent.database import get_database
            import os

            db = get_database()
            data = {
                role: {"models": list(cfg.model_ids)}
                for role, cfg in self._roles.items()
            }
            blob = json.dumps(data)
            db.save_api_key("_ROLE_MODELS_", blob)
            os.environ["_ROLE_MODELS_"] = blob
            logger.info("Saved {} role mappings to DB", len(data))
        except Exception as e:
            logger.warning("Failed to save role mappings to DB: {}", e)

    def load_from_config(self) -> None:
        """Load role assignments from CONFIG.

        Handles both new ``role_models`` dict and legacy flat fields:
        ``tts_model``, ``embedding_model``, ``image_generation_model``,
        ``extraction_model``.
        """
        from suzent.config import CONFIG

        # New-style role_models dict
        role_models = getattr(CONFIG, "role_models", None)
        if role_models:
            self.load_from_dict(role_models)

        # Legacy flat fields → role mapping (fallback if not set via role_models)
        _legacy_map = {
            ModelRole.TTS: "tts_model",
            ModelRole.EMBEDDING: "embedding_model",
            ModelRole.IMAGE_GENERATION: "image_generation_model",
            ModelRole.CHEAP: "extraction_model",
        }
        for role, attr in _legacy_map.items():
            if not self.has_role(role):
                val = getattr(CONFIG, attr, None)
                if val:
                    self.set_role(role, [val])


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: Optional[RoleRouter] = None


def get_role_router() -> RoleRouter:
    """Get or create the global RoleRouter singleton.

    On first call, loads from DB then fills gaps from CONFIG.
    """
    global _instance
    if _instance is not None:
        return _instance

    router = RoleRouter()
    router.load_from_db()
    router.load_from_config()
    _instance = router
    return router
