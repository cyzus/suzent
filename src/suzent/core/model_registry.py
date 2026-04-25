"""
Model capabilities registry.

Loads model metadata (context window, pricing, capability flags) from
``config/capabilities/{provider}.json`` (per-provider files) and the legacy
``config/model_capabilities.json`` (global overrides applied last).

Provides fast lookups used by context compression, role routing, cost
estimation, and the frontend UI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

_PROJECT_DIR = Path(__file__).resolve().parents[3]
_CAPABILITIES_DIR = _PROJECT_DIR / "config" / "capabilities"
_CAPABILITIES_PATH = _PROJECT_DIR / "config" / "model_capabilities.json"


@dataclass(frozen=True)
class ModelCapabilities:
    """Immutable capability descriptor for a single model."""

    mode: str = "chat"  # chat | embedding | image_generation | tts
    max_input_tokens: int = 0
    max_output_tokens: int = 0
    input_cost_per_token: float = 0.0
    output_cost_per_token: float = 0.0
    output_vector_size: int = 0  # embedding models only
    supports_vision: bool = False
    supports_function_calling: bool = False
    supports_reasoning: bool = False
    supports_prompt_caching: bool = False
    supports_response_schema: bool = False

    @property
    def context_window(self) -> int:
        return self.max_input_tokens + self.max_output_tokens

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_cost_per_token
            + output_tokens * self.output_cost_per_token
        )


def _parse_model_entry(attrs: dict) -> ModelCapabilities:
    return ModelCapabilities(
        mode=attrs.get("mode", "chat"),
        max_input_tokens=attrs.get("max_input_tokens", 0),
        max_output_tokens=attrs.get("max_output_tokens", 0),
        input_cost_per_token=attrs.get("input_cost_per_token", 0.0),
        output_cost_per_token=attrs.get("output_cost_per_token", 0.0),
        output_vector_size=attrs.get("output_vector_size", 0),
        supports_vision=attrs.get("supports_vision", False),
        supports_function_calling=attrs.get("supports_function_calling", False),
        supports_reasoning=attrs.get("supports_reasoning", False),
        supports_prompt_caching=attrs.get("supports_prompt_caching", False),
        supports_response_schema=attrs.get("supports_response_schema", False),
    )


def _load_file(path: Path, result: Dict[str, ModelCapabilities]) -> None:
    """Merge models from a single capabilities JSON file into result."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        for model_id, attrs in raw.get("models", {}).items():
            if model_id.startswith("_"):
                continue  # skip example/doc keys
            try:
                result[model_id] = _parse_model_entry(attrs)
            except Exception as exc:
                logger.warning(
                    "Skipping malformed entry '{}' in {}: {}", model_id, path.name, exc
                )
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load capabilities from {}: {}", path, exc)


def _load_capabilities() -> Dict[str, ModelCapabilities]:
    result: Dict[str, ModelCapabilities] = {}

    # 1. Per-provider files from config/capabilities/*.json (alphabetical order)
    if _CAPABILITIES_DIR.exists():
        for cap_file in sorted(_CAPABILITIES_DIR.glob("*.json")):
            _load_file(cap_file, result)

    # 2. Global override file applied last (takes precedence over per-provider)
    if _CAPABILITIES_PATH.exists():
        _load_file(_CAPABILITIES_PATH, result)

    logger.info("Loaded capabilities for {} models", len(result))
    return result


_LITELLM_PRICES_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)

# LiteLLM mode → our mode (None = skip that entry)
_LITELLM_MODE_MAP: dict[str, str | None] = {
    "chat": "chat",
    "completion": "chat",
    "embedding": "embedding",
    "image_generation": "image_generation",
    "audio_speech": "tts",
    "audio_transcription": None,  # STT — not a role we manage
    "moderations": None,
    "rerank": None,
}


async def sync_from_litellm() -> dict[str, int]:
    """Fetch capability data from LiteLLM's model_prices_and_context_window.json
    and merge it into per-provider capability files.

    Strategy:
    - Pricing and context window are always overwritten (LiteLLM is authoritative).
    - Capability flags (supports_vision, supports_function_calling, etc.) are
      also overwritten from LiteLLM — use ``config/model_capabilities.json``
      for manual overrides (it is applied last).
    - Models not in LiteLLM (e.g. manually added via Fetch) are preserved as-is.

    Returns dict of {provider_id: models_updated}.
    """
    import httpx

    # Build the set of provider IDs (including aliases) we actually manage
    from suzent.core.providers.catalog import PROVIDER_REGISTRY as _PR

    known_providers: set[str] = set()
    for _spec in _PR:
        known_providers.add(_spec.id)
        for _alias in _spec.aliases:
            known_providers.add(_alias)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(_LITELLM_PRICES_URL)
        resp.raise_for_status()
        raw: dict = resp.json()

    # Group entries that carry a provider prefix (e.g. "openai/gpt-4o"),
    # restricted to providers we manage.
    by_provider: dict[str, dict[str, dict]] = {}
    for key, info in raw.items():
        if not isinstance(info, dict) or "/" not in key:
            continue
        provider_id = key.split("/", 1)[0]
        if provider_id not in known_providers:
            continue
        by_provider.setdefault(provider_id, {})[key] = info

    _CAPABILITIES_DIR.mkdir(parents=True, exist_ok=True)
    stats: dict[str, int] = {}

    for provider_id, models in by_provider.items():
        cap_file = _CAPABILITIES_DIR / f"{provider_id}.json"
        existing: dict = {}
        if cap_file.exists():
            try:
                existing = json.loads(cap_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass

        curr: dict[str, dict] = existing.get("models", {})
        updated = 0

        for model_id, info in models.items():
            litellm_mode = info.get("mode", "chat")
            mapped_mode = _LITELLM_MODE_MAP.get(litellm_mode, "chat")
            if mapped_mode is None:
                continue  # skip STT / moderation / rerank

            entry: dict = dict(curr.get(model_id, {}))  # preserve existing fields
            entry["mode"] = mapped_mode

            # Pricing & context window — overwrite from LiteLLM
            for src, dst in (
                ("max_input_tokens", "max_input_tokens"),
                ("max_output_tokens", "max_output_tokens"),
                ("input_cost_per_token", "input_cost_per_token"),
                ("output_cost_per_token", "output_cost_per_token"),
                ("output_vector_size", "output_vector_size"),
            ):
                val = info.get(src)
                if val is not None:
                    entry[dst] = val

            # Capability flags — overwrite from LiteLLM
            for flag in (
                "supports_vision",
                "supports_function_calling",
                "supports_response_schema",
                "supports_reasoning",
                "supports_prompt_caching",
            ):
                val = info.get(flag)
                if val is not None:
                    entry[flag] = bool(val)

            curr[model_id] = entry
            updated += 1

        if updated:
            existing["models"] = curr
            cap_file.write_text(
                json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            stats[provider_id] = updated

    logger.info(
        "LiteLLM capability sync complete: {} providers, {} total models",
        len(stats),
        sum(stats.values()),
    )
    return stats


def save_discovered_models(provider_id: str, model_ids: list[str]) -> None:
    """Persist newly discovered model IDs to config/capabilities/{provider_id}.json.

    Only adds models that are not already present; never overwrites curated data.
    """
    _CAPABILITIES_DIR.mkdir(parents=True, exist_ok=True)
    cap_file = _CAPABILITIES_DIR / f"{provider_id}.json"

    existing: dict = {}
    if cap_file.exists():
        try:
            existing = json.loads(cap_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    models: dict = existing.get("models", {})
    added = 0
    for model_id in model_ids:
        if model_id not in models:
            models[model_id] = {"mode": "chat"}
            added += 1

    if added > 0:
        existing["models"] = models
        cap_file.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("Added {} new model(s) to {}", added, cap_file.name)


class ModelRegistry:
    """
    Singleton registry for model capabilities.

    Usage::

        registry = get_model_registry()
        caps = registry.get_capabilities("openai/gpt-4.1")
        if caps and caps.supports_vision:
            ...
    """

    def __init__(self) -> None:
        self._capabilities = _load_capabilities()

    def get_capabilities(self, model_id: str) -> Optional[ModelCapabilities]:
        """Look up capabilities for a model ID. Returns None if not registered."""
        return self._capabilities.get(model_id)

    def get_context_window(self, model_id: str) -> int:
        """Return total context window size, or 0 if unknown."""
        caps = self.get_capabilities(model_id)
        return caps.context_window if caps else 0

    def supports_vision(self, model_id: str) -> bool:
        """Check if a model supports vision/image input.

        Returns False for unknown models (strict). Run capability sync to
        populate data for newly discovered models.
        """
        caps = self.get_capabilities(model_id)
        return caps.supports_vision if caps is not None else False

    def supports_function_calling(self, model_id: str) -> bool:
        """Check if a model supports function/tool calling."""
        caps = self.get_capabilities(model_id)
        return caps.supports_function_calling if caps is not None else True

    def supports_reasoning(self, model_id: str) -> bool:
        """Check if a model supports extended thinking/reasoning."""
        caps = self.get_capabilities(model_id)
        return caps.supports_reasoning if caps is not None else False

    def estimate_cost(
        self, model_id: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Estimate call cost in USD. Returns 0.0 if model is not registered."""
        caps = self.get_capabilities(model_id)
        return caps.estimate_cost(input_tokens, output_tokens) if caps else 0.0

    def list_models(self, *, mode: Optional[str] = None) -> list[str]:
        """List all registered model IDs, optionally filtered by mode."""
        if mode is None:
            return list(self._capabilities.keys())
        return [mid for mid, caps in self._capabilities.items() if caps.mode == mode]

    def reload(self) -> None:
        """Hot-reload capabilities from disk."""
        self._capabilities = _load_capabilities()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry_instance: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    """Get the global ModelRegistry singleton."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ModelRegistry()
    return _registry_instance
