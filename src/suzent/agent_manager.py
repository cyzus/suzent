"""
Agent management module for creating and managing pydantic-ai agents.

This module handles the lifecycle of AI agents including:
- Creating pydantic-ai Agent instances with specified configurations
- Managing MCP server toolsets
- Managing global agent instances
"""

import asyncio
import os
from typing import Optional, Dict, Any, List, Set, cast

from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessHistory, ToolSearch
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import DeferredToolRequests

from suzent.core.agent_deps import AgentDeps
from suzent.core.model_factory import build_thinking_settings, create_pydantic_ai_model
from suzent.core.providers import get_enabled_models_from_db

from suzent.config import CONFIG
from suzent.logger import get_logger
from suzent.prompts import (
    CONTEXT_PRECEDENCE,
    STATIC_INSTRUCTIONS,
    register_dynamic_instructions,
)
from suzent.skills import get_skill_manager

# Import memory lifecycle functions (for backward compatibility re-exports)

# Suppress LiteLLM's verbose logging
os.environ["LITELLM_LOG"] = "ERROR"

logger = get_logger(__name__)


# --- Agent State ---
agent_instance: Optional[Agent] = None
agent_config: Optional[dict] = None
agent_lock = asyncio.Lock()

# Tools hidden by the user after native ToolSearch discovered them. This is
# process-local UI state; the durable discovery record remains in message history.
_suppressed_tools_by_chat: Dict[str, Set[str]] = {}


def get_suppressed_tools(chat_id: str) -> Set[str]:
    return _suppressed_tools_by_chat.get(chat_id, set())


def suppress_tool(chat_id: str, tool_name: str) -> None:
    _suppressed_tools_by_chat.setdefault(chat_id, set()).add(tool_name)


def clear_suppressed_tools(chat_id: str) -> None:
    _suppressed_tools_by_chat.pop(chat_id, None)


def _build_mcp_servers(config: Dict[str, Any]) -> List:
    """
    Build MCP server toolset instances from the enabled servers in config.

    Returns MCP toolsets that can be passed to a pydantic-ai Agent.
    """
    from suzent.core import mcp_store as _mcp_store

    # JSON file is the source of truth; config dict can override for special callers
    _defaults = _mcp_store.as_agent_config()
    mcp_enabled = config.get("mcp_enabled") or _defaults["mcp_enabled"]
    mcp_headers = config.get("mcp_headers") or _defaults["mcp_headers"]
    mcp_stdio_params = config.get("mcp_stdio_params") or _defaults["mcp_stdio_params"]

    raw_mcp_urls = config.get("mcp_urls") or _defaults["mcp_urls"]

    # Parse mcp_urls to handle both simple and nested formats (legacy config.yaml support)
    mcp_urls = {}

    if isinstance(raw_mcp_urls, list):
        for i, url in enumerate(raw_mcp_urls):
            mcp_urls[f"mcp-url-{i}"] = url
    elif isinstance(raw_mcp_urls, dict):
        for name, value in raw_mcp_urls.items():
            if isinstance(value, str):
                mcp_urls[name] = value
            elif isinstance(value, dict):
                mcp_urls[name] = value.get("url", "")
                if value.get("headers") and name not in mcp_headers:
                    mcp_headers[name] = value["headers"]

    servers = []

    # Build URL servers
    for name, url in mcp_urls.items():
        if mcp_enabled.get(name, False) and url:
            headers = mcp_headers.get(name)
            server = MCPToolset(
                url,
                headers=headers,
                id=name,
            ).prefixed(name)
            servers.append(server)

    # Build stdio servers
    if mcp_stdio_params:
        for name, params in mcp_stdio_params.items():
            if mcp_enabled.get(name, False):
                transport = StdioTransport(
                    command=params["command"],
                    args=params.get("args", []),
                    env=params.get("env"),
                )
                server = MCPToolset(transport, id=name).prefixed(name)
                servers.append(server)

    return servers


async def probe_mcp_server(
    entry: Dict[str, Any], timeout: float | None = None
) -> Dict[str, Any]:
    """Attempt to connect to a single MCP server and list its tools.

    `entry` is a row from mcp_store (type/url/headers/command/args/env).
    On success returns {"ok": True, "count": int, "tools": [{"name", "description"}]};
    on failure {"ok": False, "error": str}.

    stdio servers get a much longer default timeout: the first `uv tool run` /
    `npx` invocation may download and install the package before the server
    starts speaking, which can take well over a minute on a cold cache.
    """
    import asyncio

    is_stdio = entry.get("type") == "stdio"
    if timeout is None:
        timeout = 90.0 if is_stdio else 15.0

    has_url = entry.get("type") == "url" and entry.get("url")
    has_cmd = is_stdio and entry.get("command")
    if not has_url and not has_cmd:
        return {"ok": False, "error": "Server has no url or command configured"}

    def _build():
        if has_url:
            return MCPToolset(entry["url"], headers=entry.get("headers"))
        return MCPToolset(
            StdioTransport(
                command=entry["command"],
                args=entry.get("args") or [],
                env=entry.get("env"),
            )
        )

    async def _connect() -> list[dict[str, str]]:
        # Re-create the server per attempt; a half-started transport cannot be reused.
        try:
            srv = _build()
        except Exception as e:  # noqa: BLE001 - bad config surfaces to caller
            raise RuntimeError(f"Invalid server config: {e}") from e
        async with srv:
            tools = await srv.list_tools()
            return [
                {
                    "name": getattr(t, "name", ""),
                    "description": (getattr(t, "description", "") or "").strip(),
                }
                for t in tools
            ]

    # stdio startup over `uv tool run` / `npx` can transiently break the pipe before
    # the handshake settles; retry those a couple times before giving up.
    attempts = 3 if is_stdio else 1
    last_error: str | None = None
    for attempt in range(attempts):
        try:
            tools = await asyncio.wait_for(_connect(), timeout=timeout)
            return {"ok": True, "count": len(tools), "tools": tools}
        except asyncio.TimeoutError:
            hint = (
                " — the command may still be installing its package on first run; "
                "try again once it is cached"
                if is_stdio
                else ""
            )
            return {"ok": False, "error": f"Timed out after {timeout:.0f}s{hint}"}
        except Exception as e:  # noqa: BLE001 - surface connection failure
            last_error = _flatten_error(e)
            if attempt < attempts - 1 and _is_transient_stdio_error(last_error):
                await asyncio.sleep(1.0 * (attempt + 1))
                continue
            break

    return {"ok": False, "error": last_error or "Connection failed"}


def _flatten_error(exc: BaseException) -> str:
    """Produce a readable message, unwrapping anyio/TaskGroup ExceptionGroups."""
    # ExceptionGroup (Python 3.11+) hides the real cause behind a generic message.
    inner = getattr(exc, "exceptions", None)
    if inner:
        return "; ".join(_flatten_error(e) for e in inner)
    name = exc.__class__.__name__
    msg = str(exc).strip()
    if name == "BrokenResourceError" and not msg:
        # The child process closed the pipe before the handshake completed —
        # usually it exited early (bad args, crash, or still warming up).
        return "Server process closed the connection before responding (it may have exited early or is still starting)"
    return msg or name


def _is_transient_stdio_error(message: str) -> bool:
    """True for stdio startup races worth retrying (broken/closed pipe, EOF)."""
    lowered = message.lower()
    return any(
        marker in lowered
        for marker in (
            "brokenresource",
            "closed the connection",
            "closedresource",
            "eof",
        )
    )


def create_agent(config: Dict[str, Any]) -> Agent[AgentDeps, str]:
    """
    Creates a pydantic-ai Agent based on the provided configuration.

    Args:
        config: Configuration dictionary containing:
            - model: Model identifier (e.g., "gemini/gemini-2.5-pro")
            - tools: List of tool names to enable
            - memory_enabled: Whether to inject memory context (default: False).
              Does NOT control the memory_search tool, which is equipped via `tools`.
            - mcp_urls: Optional MCP server URLs
            - instructions: Optional custom instructions

    Returns:
        Configured pydantic-ai Agent instance.
    """
    # --- Validate model ---
    enabled_models = get_enabled_models_from_db()

    if not enabled_models:
        raise ValueError(
            "No LLM models are enabled. Please configure a provider in Settings."
        )

    model_id = config.get("model")

    if not model_id or model_id not in enabled_models:
        fallback = enabled_models[0]
        if model_id:
            logger.warning(
                f"Requested model '{model_id}' is not enabled. Falling back to '{fallback}'."
            )
        model_id = fallback

    model = create_pydantic_ai_model(model_id)

    # --- Resolve thinking / reasoning effort ---
    # Empty when the caller left it on "auto", which keeps each provider's own
    # default (Gemini, for instance, already streams thought summaries). The
    # provider prefix matters: self-hosted servers take a different switch.
    thinking_settings = build_thinking_settings(
        config.get("thinking"), model_id.partition("/")[0]
    )

    # --- Build tool list ---
    tool_names = (config.get("tools") or CONFIG.default_tools).copy()

    from suzent.tools.registry import (
        expand_tool_dependencies,
        get_deferred_tool_functions,
        group_tools_by_capability,
        get_tool_function,
        get_tool_session_guidance,
    )

    tool_names = expand_tool_dependencies(tool_names)
    capability_groups = group_tools_by_capability(tool_names)
    capability_tool_names = {
        tool_name for names in capability_groups.values() for tool_name in names
    }
    tool_functions = []
    enabled_tool_names = set(tool_names)
    # SkillTool / SocialMessageTool are equipped by their own auto-equip logic below,
    # so skip them in the normal loop. MemorySearchTool is NOT auto-equipped: it is a
    # regular sidebar-toggleable equipment tool, equipped when present in `tools`. The
    # global memory toggle (`memory_enabled`) only governs memory *context injection*,
    # not whether the search tool is available.
    _auto_equipped = {
        "SkillTool",
        "SocialMessageTool",
    }

    for tool_name in tool_names:
        if tool_name in _auto_equipped:
            continue
        if tool_name in capability_tool_names:
            continue
        fn = get_tool_function(tool_name)
        if fn:
            tool_functions.append(fn)
        else:
            logger.warning(f"Tool function not found for: {tool_name}")

    # All remaining deferrable tools are registered once with defer_loading=True.
    # Pydantic AI exposes its native provider-side search where supported and
    # transparently falls back to a local keyword search elsewhere.
    tool_functions.extend(get_deferred_tool_functions(enabled_tool_names))

    # Auto-equip SkillTool if any skills are enabled
    skill_manager = get_skill_manager()
    has_enabled_skills = getattr(skill_manager, "has_enabled_skills", None)
    global_skills_enabled = (
        bool(has_enabled_skills())
        if callable(has_enabled_skills)
        else bool(getattr(skill_manager, "enabled_skills", set()))
    )
    if global_skills_enabled or config.get("_has_discovered_skills"):
        fn = get_tool_function("SkillTool")
        if fn and fn not in tool_functions:
            tool_functions.append(fn)
            enabled_tool_names.add("SkillTool")
            logger.info(
                f"SkillTool equipped ({len(skill_manager.enabled_skills)} skills enabled)"
            )

    # Auto-equip SocialMessageTool
    social_ctx = config.get("social_context")
    if (
        social_ctx or "SocialMessageTool" in tool_names
    ) and "SocialMessageTool" not in capability_tool_names:
        fn = get_tool_function("SocialMessageTool")
        if fn and fn not in tool_functions:
            tool_functions.append(fn)
            enabled_tool_names.add("SocialMessageTool")

    # --- Build MCP servers ---
    mcp_servers = _build_mcp_servers(config)

    # --- Build instructions ---
    base_instructions = config.get("instructions", CONFIG.instructions)
    session_guidance_items = get_tool_session_guidance(sorted(enabled_tool_names))
    # A caller-supplied prompt replaces STATIC_INSTRUCTIONS outright, so the
    # precedence rules have to be prepended or a custom agent has nothing to
    # resolve a conflict against — and it still reads repository files and tool
    # output, which is where the conflict comes from.
    _custom_instructions = config.get("static_instructions")
    static_instructions = (
        CONTEXT_PRECEDENCE + "\n" + _custom_instructions
        if _custom_instructions
        else STATIC_INSTRUCTIONS
    )

    # --- Create pydantic-ai Agent ---
    # Mid-run context compaction: the history processor runs before every model
    # request within a run, so a tool-heavy turn that grows past the trigger
    # threshold is compacted in-flight (not only at turn boundaries). It self-guards
    # on deps.stateless, so it's safe to register for every agent.
    from suzent.core.context_compressor import make_compaction_history_processor
    from suzent.core.repository_context import (
        RepositoryContextRoots,
        build_repo_context_capabilities,
    )
    from suzent.tools.capability import RegisteredToolCapability

    from suzent.core.system_reminder import (
        make_tool_output_sanitizer_history_processor,
    )

    capabilities = [
        # Sanitizer first: it must neutralize forged reminder delimiters before
        # compaction folds tool output into a summary that we can no longer inspect.
        ProcessHistory(make_tool_output_sanitizer_history_processor()),
        ProcessHistory(make_compaction_history_processor()),
        ToolSearch(),
    ]
    project_context_dir = config.get("_project_context_dir")
    working_context_dir = config.get("_working_context_dir")
    if project_context_dir and working_context_dir:
        from pathlib import Path

        repository_root = config.get("_repository_root")
        context_roots = RepositoryContextRoots(
            project_dir=Path(project_context_dir),
            working_dir=Path(working_context_dir),
            repository_root=Path(repository_root) if repository_root else None,
        )
        capabilities.extend(build_repo_context_capabilities(context_roots))
    capabilities.extend(
        RegisteredToolCapability(capability_id, tuple(selected_tools))
        for capability_id, selected_tools in capability_groups.items()
    )

    agent = Agent(
        model,
        deps_type=AgentDeps,
        tools=tool_functions,
        toolsets=mcp_servers if mcp_servers else [],
        instructions=static_instructions,
        output_type=[str, DeferredToolRequests],
        retries={"output": 3},
        end_strategy="early",
        capabilities=capabilities,
        model_settings=cast(ModelSettings, thinking_settings)
        if thinking_settings
        else None,
    )

    register_dynamic_instructions(
        agent,
        base_instructions=base_instructions,
        session_guidance_items=session_guidance_items,
        enabled_model_ids=enabled_models,
        current_model_id=model_id,
    )

    # Store metadata for later introspection
    agent._tool_names = [tn for tn in tool_names]  # type: ignore[attr-defined]
    agent._model_id = model_id  # type: ignore[attr-defined]

    return agent


def build_agent_config(
    base_config: Optional[Dict[str, Any]] = None, require_social_tool: bool = False
) -> Dict[str, Any]:
    """
    Builds the effective configuration dictionary for a ChatProcessor turn,
    merging base configs with user preferences from the database.

    Args:
        base_config: Initial configuration overrides (e.g., from request).
        require_social_tool: If True, ensures SocialMessageTool is equipped.

    Returns:
        A dictionary containing the merged configuration.
    """
    from suzent.database import get_database

    config = base_config.copy() if base_config else {}

    try:
        db = get_database()
        if prefs := db.get_user_preferences():
            if not config.get("model") and prefs.model:
                config["model"] = prefs.model
            if not config.get("agent") and prefs.agent:
                config["agent"] = prefs.agent
            if "tools" not in config and prefs.tools is not None:
                config["tools"] = prefs.tools
            if not config.get("thinking") and prefs.thinking:
                config["thinking"] = prefs.thinking
    except Exception as e:
        logger.warning(f"Failed to load user preferences: {e}")

    # Ensure tools list exists and is populated
    tools = config.get("tools")
    if tools is None:
        tools = CONFIG.default_tools.copy()
    elif isinstance(tools, list):
        tools = tools.copy()

    if require_social_tool and "SocialMessageTool" not in tools:
        tools.append("SocialMessageTool")

    config["tools"] = tools

    return config


# Config keys that must NOT take part in the agent cache key.
#
# Everything else does, which is what keeps one project's repository
# instructions out of another's: `_project_context_dir` / `_working_context_dir`
# are set per request in chat_processor and deliberately left in the stable
# config. Adding either of them here would reintroduce cross-project bleed.
#
# `_chat_id` / `_user_id` are safe to exclude only because every scoped section
# is now resolved per run from `ctx.deps` rather than captured at construction.
_TRANSIENT_KEYS = {"_runtime", "_chat_id", "_user_id"}


async def get_or_create_agent(config: Dict[str, Any], reset: bool = False) -> Agent:
    """
    Get the current agent instance or create a new one if needed.

    Args:
        config: Agent configuration dictionary.
        reset: If True, force creation of a new agent instance.

    Returns:
        pydantic-ai Agent instance ready for use.
    """
    global agent_instance, agent_config

    def _stable_config(cfg: dict) -> dict:
        return {k: v for k, v in cfg.items() if k not in _TRANSIENT_KEYS}

    async with agent_lock:
        config_changed = _stable_config(config) != (
            _stable_config(agent_config) if agent_config else None
        )
        if config_changed and agent_config is not None:
            logger.info("Config changed - creating new agent")

        if agent_instance is None or config_changed or reset:
            # No core-memory prefetch here on purpose. The agent is cached and
            # reused across chats and users, so anything captured now would be
            # served to whoever the agent is reused for next. Core memory is
            # resolved per run from ctx.deps instead — see
            # prompts.inject_memory_context.
            agent_instance = create_agent(config)
            agent_config = config

        return agent_instance
