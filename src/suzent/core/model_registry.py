"""
Model capabilities registry.

Loads model metadata (context window, pricing, capability flags) from three
layers, later layers overlaying earlier ones:

1. ``config/capabilities/{provider}.json`` — shipped, hand-curated, tracked in
   git. Treated as read-only at runtime so ``suzent update`` (git pull) never
   conflicts with local changes.
2. ``<data dir>/capabilities/{provider}.json`` — local overlay of models found
   by runtime discovery / LiteLLM sync. Lives outside the repo; all runtime
   writes go here. Only supplies models not already shipped (curated wins).
3. ``config/model_capabilities.json`` — legacy global overrides, applied last.

Provides fast lookups used by context compression, role routing, cost
estimation, and the frontend UI.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

_PROJECT_DIR = Path(__file__).resolve().parents[3]
# Shipped, hand-curated capability files. Tracked in git; treated as read-only
# at runtime so `suzent update` (git pull) never hits local modifications.
_CAPABILITIES_DIR = _PROJECT_DIR / "config" / "capabilities"
_CAPABILITIES_PATH = _PROJECT_DIR / "config" / "model_capabilities.json"


def _local_capabilities_dir() -> Path:
    """Writable overlay for runtime-discovered capabilities.

    Lives in the user data directory (outside the repo), so auto-discovery and
    LiteLLM sync never dirty the tracked ``config/capabilities/*.json`` files.
    Loaded after the shipped files, so curated data shipped in the repo wins.
    """
    from suzent.config import get_data_dir

    return get_data_dir() / "capabilities"


def _writes_to_repo() -> bool:
    """Whether runtime discovery should write into the tracked repo dir.

    Enabled by the CLI in developer mode (``suzent start --dev`` / ``serve
    --dev``) via ``SUZENT_CAPABILITIES_TO_REPO=1``, so newly discovered models
    land in ``config/capabilities/`` ready to commit. Off by default, where
    writes go to the user-data overlay and never dirty the repo.
    """
    return os.getenv("SUZENT_CAPABILITIES_TO_REPO", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _write_target_dir() -> Path:
    """Directory that runtime discovery writes to (repo in dev, else overlay)."""
    return _CAPABILITIES_DIR if _writes_to_repo() else _local_capabilities_dir()


@dataclass(frozen=True)
class ModelCapabilities:
    """Immutable capability descriptor for a single model."""

    mode: str = "chat"  # chat | embedding | image_generation | tts
    max_input_tokens: int = 0
    max_output_tokens: int = 0
    output_vector_size: int = 0  # embedding models only
    supports_vision: bool = False
    supports_function_calling: bool = False
    supports_reasoning: bool = False
    supports_prompt_caching: bool = False
    supports_response_schema: bool = False
    input_cost_per_token: float = 0.0
    output_cost_per_token: float = 0.0

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
        output_vector_size=attrs.get("output_vector_size", 0),
        supports_vision=attrs.get("supports_vision", False),
        supports_function_calling=attrs.get("supports_function_calling", False),
        supports_reasoning=attrs.get("supports_reasoning", False),
        supports_prompt_caching=attrs.get("supports_prompt_caching", False),
        supports_response_schema=attrs.get("supports_response_schema", False),
    )


def _load_file(
    path: Path, result: Dict[str, ModelCapabilities], *, overlay: bool = False
) -> None:
    """Merge models from a single capabilities JSON file into result.

    When ``overlay`` is True, only models not already present are added, so a
    shipped curated entry is never clobbered by a runtime-discovered stub.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        for model_id, attrs in raw.get("models", {}).items():
            if model_id.startswith("_"):
                continue  # skip example/doc keys
            if overlay and model_id in result:
                continue  # shipped curated data wins
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

    # 1. Shipped per-provider files from config/capabilities/*.json (alpha order)
    if _CAPABILITIES_DIR.exists():
        for cap_file in sorted(_CAPABILITIES_DIR.glob("*.json")):
            _load_file(cap_file, result)

    # 2. Local overlay of runtime-discovered models (user data dir). Adds models
    #    not shipped in the repo; shipped curated entries above take precedence
    #    for fields they define, but overlay-only models are merged in.
    local_dir = _local_capabilities_dir()
    if local_dir.exists():
        for cap_file in sorted(local_dir.glob("*.json")):
            _load_file(cap_file, result, overlay=True)

    # 3. Global override file applied last (takes precedence over per-provider)
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


def _read_models_file(path: Path) -> dict[str, dict]:
    """Return the ``models`` dict from a capabilities file, or ``{}``."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("models", {})
    except json.JSONDecodeError:
        return {}


def _shipped_provider_models(provider_id: str) -> dict[str, dict]:
    """Curated models shipped in the repo for a provider (read-only)."""
    return _read_models_file(_CAPABILITIES_DIR / f"{provider_id}.json")


def _local_provider_models(provider_id: str) -> dict[str, dict]:
    """Runtime-discovered models stored in the local overlay for a provider."""
    return _read_models_file(_local_capabilities_dir() / f"{provider_id}.json")


def _read_provider_models(provider_id: str) -> dict[str, dict]:
    """Merge a provider's models from the shipped file and the local overlay.

    Shipped (curated) entries take precedence; overlay supplies discovered
    models not present in the shipped file.
    """
    merged: dict[str, dict] = dict(_local_provider_models(provider_id))
    merged.update(_shipped_provider_models(provider_id))  # curated wins
    return merged


def _write_provider(provider_id: str, models: dict[str, dict]) -> None:
    """Persist a provider's models to the active write target.

    In developer mode (``SUZENT_CAPABILITIES_TO_REPO``) this is the tracked
    ``config/capabilities/`` dir, so discovered models can be committed. By
    default it is the user-data overlay, where model IDs already present in the
    shipped repo file are dropped — the shipped curated entry wins at load time,
    so an overlay copy is redundant and would go stale if the shipped entry is
    later edited.
    """
    target_dir = _write_target_dir()
    to_repo = target_dir == _CAPABILITIES_DIR

    models = {mid: attrs for mid, attrs in models.items() if not mid.startswith("_")}
    if not to_repo:
        shipped = _shipped_provider_models(provider_id)
        models = {mid: attrs for mid, attrs in models.items() if mid not in shipped}

    cap_file = target_dir / f"{provider_id}.json"

    # Overlay only: nothing provider-specific left — remove a stale empty file.
    if not models and not to_repo:
        if cap_file.exists():
            try:
                cap_file.unlink()
            except OSError:
                pass
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if cap_file.exists():
        try:
            existing = json.loads(cap_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    if not to_repo:
        # Stamp the overlay doc string. Repo files keep their curated _doc as-is.
        existing["_doc"] = (
            "Runtime-discovered model capabilities (local overlay). "
            "Auto-generated; safe to delete. Curated defaults live in "
            "config/capabilities/ inside the repo."
        )
    existing["models"] = models
    cap_file.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
    )


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

    stats: dict[str, int] = {}

    for provider_id, models in by_provider.items():
        # Read merged shipped + overlay so we preserve any existing fields, but
        # write results only to the local overlay (never the tracked repo file).
        curr: dict[str, dict] = _read_provider_models(provider_id)
        updated = 0

        for model_id, info in models.items():
            litellm_mode = info.get("mode", "chat")
            mapped_mode = _LITELLM_MODE_MAP.get(litellm_mode, "chat")
            if mapped_mode is None:
                continue  # skip STT / moderation / rerank

            entry: dict = dict(curr.get(model_id, {}))  # preserve existing fields
            entry["mode"] = mapped_mode

            # Context window — overwrite from LiteLLM
            for src, dst in (
                ("max_input_tokens", "max_input_tokens"),
                ("max_output_tokens", "max_output_tokens"),
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
            _write_provider(provider_id, curr)
            stats[provider_id] = updated

    logger.info(
        "LiteLLM capability sync complete: {} providers, {} total models",
        len(stats),
        sum(stats.values()),
    )
    return stats


def _is_auto_discovered(entry: dict) -> bool:
    """True if an entry is a bare discovery stub (only a ``mode`` key, no
    curated metadata). Such entries are safe to prune when the provider no
    longer lists the model; hand-curated entries (with token limits, flags,
    pricing, etc.) are always preserved.
    """
    return set(entry.keys()) <= {"mode"}


def prune_stale_models(provider_id: str, live_model_ids: list[str]) -> list[str]:
    """Remove auto-discovered model stubs that the provider no longer offers.

    Operates on the active write target (the overlay by default, or the tracked
    repo dir in developer mode). Bare discovery stubs (see
    :func:`_is_auto_discovered`) absent from the live catalog are removed;
    curated entries are never touched.

    Returns the list of removed model IDs. No-op (returns ``[]``) when the live
    catalog is empty, to avoid wiping a file on a failed/partial discovery.
    """
    if not live_model_ids:
        return []

    target_dir = _write_target_dir()
    cap_file = target_dir / f"{provider_id}.json"
    models: dict = _read_models_file(cap_file)
    if not models:
        return []

    live = set(live_model_ids)
    removed: list[str] = []

    for model_id in list(models):
        if model_id.startswith("_"):
            continue  # preserve doc/example keys
        if model_id in live:
            continue
        if _is_auto_discovered(models[model_id]):
            del models[model_id]
            removed.append(model_id)

    if removed:
        _write_provider(provider_id, models)
        logger.info("Pruned {} stale model(s) from {}", len(removed), cap_file.name)

    return removed


def save_discovered_models(provider_id: str, model_ids: list[str]) -> None:
    """Persist newly discovered model IDs to the active write target.

    Writes to the user-data overlay by default, or to the tracked repo dir in
    developer mode (``SUZENT_CAPABILITIES_TO_REPO``). Only adds models not
    already present in the shipped file or the overlay; never overwrites
    curated data.
    """
    # "Already present" is judged against the merged shipped + overlay view, so
    # a model already curated in the repo isn't re-added as a bare stub.
    models: dict = _read_provider_models(provider_id)
    added = 0
    for model_id in model_ids:
        if model_id not in models:
            models[model_id] = {"mode": "chat"}
            added += 1

    if added > 0:
        _write_provider(provider_id, models)
        logger.info("Added {} new model(s) to {}.json", added, provider_id)


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
