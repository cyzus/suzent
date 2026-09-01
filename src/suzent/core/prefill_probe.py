"""Liveness probes for local OpenAI-compatible inference servers.

A self-hosted server streams nothing at all while it prefills -- measured
against SGLang, a 135k-token prompt produced 130 seconds of total silence
before even the HTTP response headers arrived. So the client cannot tell a
server that is working hard from one that has wedged, and any deadline it picks
is a guess that is wrong in one direction or the other.

Those servers do publish the answer out of band. SGLang's and vLLM's Prometheus
endpoints expose a monotonic count of prefill tokens processed, which advances
in chunked-prefill-sized steps throughout the silent window. Polling it turns
"has it been too long?" into "is the server still doing work?" -- a question
with an actual answer.

Hosted providers have no equivalent endpoint, so `make_prefill_probe` returns
None for them and the caller falls back to a time-based deadline.
"""

from __future__ import annotations

import os
import re
from typing import Awaitable, Callable, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

# Providers that speak the OpenAI API from a server the user runs themselves,
# and therefore expose an admin surface the client is allowed to poll.
_PROBEABLE_PROVIDERS = frozenset({"sglang", "vllm"})

# Monotonic counters of prefill work, most specific first. Any increase means
# the server is alive and making progress; the absolute value is meaningless.
_PROGRESS_COUNTERS: dict[str, tuple[str, ...]] = {
    "sglang": ("sglang:prefill_effective_tokens_total", "sglang:num_requests_total"),
    "vllm": ("vllm:prompt_tokens_total", "vllm:num_requests_running"),
}

_METRICS_TIMEOUT_SECONDS = 5.0

ProbeFn = Callable[[], Awaitable[Optional[float]]]


def _resolve_base_url(provider: str) -> Optional[str]:
    """Find the configured base URL for a provider, secrets before environment."""
    from suzent.core.providers.catalog import PROVIDER_REGISTRY_BY_ID

    spec = PROVIDER_REGISTRY_BY_ID.get(provider)
    if spec is None:
        return None

    for field in spec.fields:
        env_key = field.get("key", "")
        if "BASE_URL" not in env_key:
            continue
        try:
            from suzent.core.secrets import get_secret_manager

            value = get_secret_manager().get(env_key)
        except Exception:
            value = None
        value = value or os.environ.get(env_key)
        if value:
            return value
        break

    return spec.base_url


def metrics_url(base_url: str) -> str:
    """Map an OpenAI-compatible base URL to the server's Prometheus endpoint.

    The metrics endpoint sits at the server root, not under the ``/v1`` prefix
    that the chat API is served from.
    """
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    return root + "/metrics"


def parse_progress(body: str, counters: tuple[str, ...]) -> Optional[float]:
    """Sum a Prometheus exposition's samples for the first counter present.

    Summed rather than first-match because a tensor-parallel server reports one
    labelled series per rank; reading a single rank would miss work done on the
    others and read as a stall.
    """
    for name in counters:
        matches = re.findall(
            rf"^{re.escape(name)}(?:\{{[^}}]*\}})? ([0-9.eE+-]+)$", body, re.M
        )
        if matches:
            try:
                return sum(float(value) for value in matches)
            except ValueError:
                continue
    return None


def make_prefill_probe(model_id: Optional[str]) -> Optional[ProbeFn]:
    """Return a probe for this model's server, or None if it has no admin surface.

    The probe answers "how much prefill work has this server done in total?".
    It returns None whenever the answer is unavailable -- an unreachable server,
    metrics not enabled, an unrecognised exposition -- and the caller must treat
    None as "unknown", never as "stalled".
    """
    if not model_id or "/" not in model_id:
        return None
    provider = model_id.split("/", 1)[0]
    if provider not in _PROBEABLE_PROVIDERS:
        return None

    base_url = _resolve_base_url(provider)
    if not base_url:
        return None

    from suzent.core.providers.helpers import resolve_api_key

    url = metrics_url(base_url)
    api_key = resolve_api_key(provider)
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    counters = _PROGRESS_COUNTERS.get(provider, ())
    # One failure means metrics are off or the URL is wrong; both are permanent
    # for this run, and retrying every few seconds would just add latency to a
    # wait that is already too long.
    disabled = False

    async def probe() -> Optional[float]:
        nonlocal disabled
        if disabled:
            return None
        try:
            import httpx

            async with httpx.AsyncClient(timeout=_METRICS_TIMEOUT_SECONDS) as client:
                response = await client.get(url, headers=headers)
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            value = parse_progress(response.text, counters)
        except Exception as exc:
            disabled = True
            logger.debug(
                "[PrefillProbe] {} has no usable metrics at {} ({}); "
                "falling back to a time-based deadline.",
                provider,
                url,
                exc,
            )
            return None
        if value is None:
            disabled = True
            logger.debug(
                "[PrefillProbe] {} exposes no known progress counter at {}.",
                provider,
                url,
            )
        return value

    return probe
