"""Per-chat prompt-cache routing for providers that route requests by a client key.

OpenAI and the ChatGPT subscription backend cache prompt prefixes per machine and
pick the machine from a hash of the prefix. Without a stable per-conversation key,
consecutive requests of one chat land on machines that never saw its prefix, and
cache hits swing between almost everything and almost nothing on a context that
only grew. The key has to be the chat being served, so it is applied per request
rather than baked into the model, which is cached and shared across chats.
"""

from __future__ import annotations

import hashlib
import os
import weakref
from collections import OrderedDict
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Sequence
from urllib.parse import urlparse

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.capabilities.abstract import WrapModelRequestHandler
from pydantic_ai.messages import InstructionPart, ModelResponse
from pydantic_ai.models import Model, ModelRequestContext
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import ToolDefinition

from suzent.core.agent_deps import AgentDeps
from suzent.logger import get_logger

logger = get_logger(__name__)


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


# OpenAI caps `prompt_cache_key` at 64 characters, and A2A chat ids embed the
# caller's context id, so a long id is hashed to a stable key of that length.
_MAX_CACHE_KEY_CHARS = 64


def cache_key_for(chat_id: str) -> str:
    if len(chat_id) <= _MAX_CACHE_KEY_CHARS:
        return chat_id
    return hashlib.sha256(chat_id.encode()).hexdigest()


def cache_routing_settings(
    model: Model, chat_id: str, settings: ModelSettings | None = None
) -> ModelSettings | None:
    """Return ``settings`` with the chat's cache routing, if the model takes one."""
    routing = _resolve_routing(model)
    if routing is None or not chat_id:
        return settings
    key = cache_key_for(chat_id)
    merged: dict[str, Any] = dict(settings or {})
    match routing:
        case CacheRouting.PROMPT_CACHE_KEY:
            merged["openai_prompt_cache_key"] = key
        case CacheRouting.SESSION_HEADER:
            merged["extra_headers"] = {
                **(merged.get("extra_headers") or {}),
                "session_id": key,
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
            getattr(ctx.deps, "prompt_cache_chat_id", "")
            or getattr(ctx.deps, "chat_id", "")
            or "",
            request_context.model_settings,
        )
        return await handler(request_context)


# ─── Forked sub-agents ────────────────────────────────────────────────────────
#
# A sub-agent that inherits its parent's history can read the parent's cached
# prefix only if everything before that history is byte-identical: tools, then
# system prompt. Building the fork's prompt from its own deps cannot promise
# that -- its chat id, permission mode and memory pin all differ -- so the
# fork is sent the exact instruction parts its parent last sent instead, and
# its tool definitions are checked against the parent's.
#
# In memory on purpose: a fork is spawned from its parent's running turn, in
# this process, and after a restart an unpinned fork only loses the cache hit.

_MAX_TRACKED_CHATS = 256
_DIAGNOSTICS_ENV = "SUZENT_CACHE_DIAGNOSTICS"
_ANTHROPIC_API_HOST = "api.anthropic.com"


@dataclass(frozen=True)
class PrefixSnapshot:
    instruction_parts: tuple[InstructionPart, ...]
    tool_defs: tuple[ToolDefinition, ...]


_TURN_CONFIGS: OrderedDict[str, dict[str, Any]] = OrderedDict()
_LATEST_PREFIXES: OrderedDict[str, PrefixSnapshot] = OrderedDict()
_FORK_PREFIXES: OrderedDict[str, PrefixSnapshot] = OrderedDict()


def _remember(store: OrderedDict, key: str, value: Any) -> None:
    store[key] = value
    store.move_to_end(key)
    while len(store) > _MAX_TRACKED_CHATS:
        store.popitem(last=False)


def record_turn_config(chat_id: str, config: dict[str, Any]) -> None:
    """Keep the config a chat's current turn built its agent from."""
    if chat_id:
        _remember(
            _TURN_CONFIGS,
            chat_id,
            {key: value for key, value in config.items() if key != "_runtime"},
        )


def turn_config(chat_id: str) -> dict[str, Any] | None:
    config = _TURN_CONFIGS.get(chat_id)
    return dict(config) if config is not None else None


def pin_fork_prefix(fork_chat_id: str, parent_chat_id: str) -> bool:
    """Send ``fork_chat_id`` the prefix ``parent_chat_id`` last sent.

    Pinned once, at spawn: a follow-up turn of the fork then matches the fork's
    own earlier requests even after the parent's prompt has moved on.
    """
    snapshot = _LATEST_PREFIXES.get(parent_chat_id)
    if snapshot is None:
        return False
    _remember(_FORK_PREFIXES, fork_chat_id, snapshot)
    return True


def _tool_signature(tool_def: ToolDefinition) -> tuple[Any, ...]:
    return (
        tool_def.name,
        tool_def.description,
        tool_def.parameters_json_schema,
        tool_def.defer_loading,
    )


def _log_tool_drift(
    chat_id: str,
    parent_defs: Sequence[ToolDefinition],
    fork_defs: Sequence[ToolDefinition],
) -> None:
    parent = {tool_def.name: _tool_signature(tool_def) for tool_def in parent_defs}
    fork = {tool_def.name: _tool_signature(tool_def) for tool_def in fork_defs}
    parent_names, fork_names = list(parent), list(fork)
    changed = sorted(
        name for name in parent.keys() & fork.keys() if parent[name] != fork[name]
    )
    if parent_names == fork_names and not changed:
        return
    logger.info(
        "Fork {} tool definitions differ from its parent's, so the cached "
        "prefix cannot be reused: missing={} added={} changed={} reordered={}",
        chat_id,
        sorted(set(parent_names) - set(fork_names)),
        sorted(set(fork_names) - set(parent_names)),
        changed,
        parent_names != fork_names and set(parent_names) == set(fork_names),
    )


def _diagnostics_enabled() -> bool:
    return os.getenv(_DIAGNOSTICS_ENV, "").strip().lower() in ("1", "true", "yes")


def _is_anthropic_api(model: Model) -> bool:
    """Diagnostics exist only on Anthropic's own API, not compatible endpoints."""
    from pydantic_ai.models.anthropic import AnthropicModel

    while isinstance(model, WrapperModel):
        model = model.wrapped
    return (
        isinstance(model, AnthropicModel)
        and urlparse(model.base_url).hostname == _ANTHROPIC_API_HOST
    )


def _log_fork_cache_result(chat_id: str, response: ModelResponse) -> None:
    usage = response.usage
    details = response.provider_details or {}
    # Anthropic leaves the key out when nothing diverged; OpenAI always reports.
    diagnostics = details.get("cache_diagnostics") or details.get(
        "prompt_cache_diagnostics"
    )
    logger.info(
        "Fork {} prompt cache: {}/{} input tokens read from cache ({:.0%}), "
        "{} written; diagnostics={}",
        chat_id,
        usage.cache_read_tokens,
        usage.input_tokens,
        usage.cache_read_tokens / usage.input_tokens if usage.input_tokens else 0.0,
        usage.cache_write_tokens,
        diagnostics,
    )


@dataclass
class ForkPrefixCapability(AbstractCapability[AgentDeps]):
    """Record each chat's prefix, and replay a parent's prefix in its forks.

    Registered last so the instruction parts it records and replaces are the
    ones every other capability has already had its say on.
    """

    async def before_model_request(
        self,
        ctx: RunContext[AgentDeps],
        request_context: ModelRequestContext,
    ) -> ModelRequestContext:
        chat_id = getattr(ctx.deps, "chat_id", "") or ""
        params = request_context.model_request_parameters
        pinned = _FORK_PREFIXES.get(chat_id)
        if pinned is None:
            if chat_id and params.instruction_parts is not None:
                _remember(
                    _LATEST_PREFIXES,
                    chat_id,
                    PrefixSnapshot(
                        tuple(params.instruction_parts), tuple(params.function_tools)
                    ),
                )
        else:
            _log_tool_drift(chat_id, pinned.tool_defs, params.function_tools)
            request_context.model_request_parameters = replace(
                params, instruction_parts=list(pinned.instruction_parts)
            )
        # Anthropic compares a request only with one that also opted in, so the
        # parent has to carry diagnostics too for a fork's first request to be
        # explained. Off by default: HIPAA-enabled organizations reject them.
        if _diagnostics_enabled() and _is_anthropic_api(request_context.model):
            request_context.model_settings = ModelSettings(
                **{
                    **(request_context.model_settings or {}),
                    "anthropic_cache_diagnostics": True,
                }
            )
        return request_context

    async def after_model_request(
        self,
        ctx: RunContext[AgentDeps],
        *,
        request_context: ModelRequestContext,
        response: ModelResponse,
    ) -> ModelResponse:
        chat_id = getattr(ctx.deps, "chat_id", "") or ""
        if chat_id in _FORK_PREFIXES:
            _log_fork_cache_result(chat_id, response)
        return response
