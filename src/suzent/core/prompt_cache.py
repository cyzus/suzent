"""Per-chat prompt-cache routing for providers that route requests by a client key.

OpenAI and the ChatGPT subscription backend cache prompt prefixes per machine and
pick the machine from a hash of the prefix. Without a stable per-conversation key,
consecutive requests of one chat land on machines that never saw its prefix, and
cache hits swing between almost everything and almost nothing on a context that
only grew. The key has to be the chat being served, so it is applied per request
rather than baked into the model, which is cached and shared across chats.
"""

from __future__ import annotations

import weakref
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.capabilities.abstract import WrapModelRequestHandler
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models import Model, ModelRequestContext
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings

from suzent.core.agent_deps import AgentDeps


class CacheRouting(StrEnum):
    # OpenAI's documented `prompt_cache_key` request field.
    PROMPT_CACHE_KEY = "prompt_cache_key"
    # The ChatGPT backend is routed the way Codex and LiteLLM route it: a
    # `session_id` header carrying the conversation id. Its body field allowlist
    # is undocumented, so `prompt_cache_key` stays stripped there.
    SESSION_HEADER = "session_header"


# Keyed by id because pydantic-ai models are unhashable dataclasses; the
# finalizer drops the entry before a recycled id could match a new model.
_ROUTING: dict[int, CacheRouting] = {}


def register_cache_routing(model: Model, routing: CacheRouting) -> None:
    key = id(model)
    if key not in _ROUTING:
        weakref.finalize(model, _ROUTING.pop, key, None)
    _ROUTING[key] = routing


def _resolve_routing(model: Model) -> CacheRouting | None:
    while True:
        routing = _ROUTING.get(id(model))
        if routing is not None or not isinstance(model, WrapperModel):
            return routing
        model = model.wrapped


def cache_routing_settings(
    model: Model, chat_id: str, settings: ModelSettings | None = None
) -> ModelSettings | None:
    """Return ``settings`` with the chat's cache routing, if the model takes one."""
    routing = _resolve_routing(model)
    if routing is None or not chat_id:
        return settings
    merged: dict[str, Any] = dict(settings or {})
    match routing:
        case CacheRouting.PROMPT_CACHE_KEY:
            merged["openai_prompt_cache_key"] = chat_id
        case CacheRouting.SESSION_HEADER:
            merged["extra_headers"] = {
                **(merged.get("extra_headers") or {}),
                "session_id": chat_id,
            }
    return ModelSettings(**merged)


@dataclass
class PromptCacheRoutingCapability(AbstractCapability[AgentDeps]):
    async def wrap_model_request(
        self,
        ctx: RunContext[AgentDeps],
        *,
        request_context: ModelRequestContext,
        handler: WrapModelRequestHandler,
    ) -> ModelResponse:
        request_context.model_settings = cache_routing_settings(
            request_context.model,
            getattr(ctx.deps, "chat_id", "") or "",
            request_context.model_settings,
        )
        return await handler(request_context)
