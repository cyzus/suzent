"""How long a provider keeps a prompt cache entry, estimated per model.

No provider reports this, so the estimate starts from what each provider
documents (or, for Anthropic, from the TTL the request asked for) and is raised
by what Suzent has seen: a request that still read from the cache after the
model sat idle for some time proves the entry lives at least that long.
Observations only ever raise the estimate, since a miss can also mean the
prefix changed.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Mapping, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

ANTHROPIC_TTL_SECONDS = {"5m": 300.0, "1h": 3600.0}

#: Documented or conservative cache lifetimes by Suzent provider id. Providers
#: left out are unknown until a cache hit has been observed.
PROVIDER_DEFAULT_TTL_SECONDS: dict[str, float] = {
    # In-memory caches cleared after 5-10 minutes of inactivity.
    "openai": 300.0,
    "chatgpt": 300.0,
    "gemini": 300.0,
    # Disk caches kept for hours.
    "deepseek": 3600.0,
}

#: Idle gaps shorter than this say nothing beyond the shortest default.
MIN_OBSERVED_GAP_SECONDS = 60.0
MAX_OBSERVED_TTL_SECONDS = 24 * 3600.0
#: A hit has to read at least this many tokens, so a shared tool or system
#: prefix kept warm by other traffic is less likely to count.
MIN_OBSERVED_CACHE_READ_TOKENS = 1024

_lock = threading.Lock()
_last_request_at: dict[str, float] = {}
_observed: Optional[dict[str, float]] = None


def _store_path() -> Path:
    from suzent.config import DATA_DIR

    return DATA_DIR / "prompt_cache_ttl.json"


def _observations() -> dict[str, float]:
    global _observed
    if _observed is None:
        try:
            raw = json.loads(_store_path().read_text(encoding="utf-8"))
            _observed = {
                str(k): float(v) for k, v in raw.items() if isinstance(v, (int, float))
            }
        except FileNotFoundError:
            _observed = {}
        except (OSError, ValueError, AttributeError) as e:
            logger.warning("Ignoring unreadable prompt cache TTL observations: {}", e)
            _observed = {}
    return _observed


def _save(observed: dict[str, float]) -> None:
    try:
        _store_path().write_text(json.dumps(observed, indent=2), encoding="utf-8")
    except OSError as e:
        logger.warning("Could not save prompt cache TTL observations: {}", e)


def _anthropic_ttl(settings: Mapping[str, Any]) -> float:
    for key in ("anthropic_cache", "anthropic_cache_messages"):
        value = settings.get(key)
        if isinstance(value, str) and value in ANTHROPIC_TTL_SECONDS:
            return ANTHROPIC_TTL_SECONDS[value]
    return ANTHROPIC_TTL_SECONDS["5m"]


def default_ttl_seconds(
    model_id: str, settings: Optional[Mapping[str, Any]] = None
) -> Optional[float]:
    """The documented TTL for ``model_id`` ("provider/model"), if known."""
    provider = model_id.split("/", 1)[0] if "/" in model_id else ""
    if provider == "anthropic":
        return _anthropic_ttl(settings or {})
    return PROVIDER_DEFAULT_TTL_SECONDS.get(provider)


def observed_ttl_seconds(model_id: str) -> Optional[float]:
    with _lock:
        return _observations().get(model_id)


def estimate_ttl_seconds(
    model_id: str, settings: Optional[Mapping[str, Any]] = None
) -> Optional[float]:
    """How long ``model_id`` likely keeps a cached prefix, or None if unknown."""
    known = [
        value
        for value in (
            default_ttl_seconds(model_id, settings),
            observed_ttl_seconds(model_id),
        )
        if value
    ]
    return max(known) if known else None


def observe_request(model_id: str, sent_at: float, cache_read_tokens: int) -> None:
    """Learn from one request: a cache hit after an idle gap raises the estimate.

    The gap is measured from the model's previous request in any chat, since
    the shared tool and instruction prefix is refreshed by every chat.
    """
    if not model_id:
        return
    with _lock:
        previous = _last_request_at.get(model_id)
        _last_request_at[model_id] = max(previous or 0.0, sent_at)
        if previous is None or cache_read_tokens < MIN_OBSERVED_CACHE_READ_TOKENS:
            return
        gap = min(sent_at - previous, MAX_OBSERVED_TTL_SECONDS)
        if gap < MIN_OBSERVED_GAP_SECONDS:
            return
        observed = _observations()
        if gap <= observed.get(model_id, 0.0):
            return
        observed[model_id] = gap
        snapshot = dict(observed)
    logger.info("Prompt cache for {} was still warm after {:.0f}s idle", model_id, gap)
    _save(snapshot)
