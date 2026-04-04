"""
Agent dependency container for pydantic-ai's RunContext dependency injection.

This dataclass replaces the per-tool context injection pattern
(set_context, set_chat_context, set_social_context) with a single
dependency object passed to every tool via RunContext[AgentDeps].
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AgentDeps:
    """
    Dependencies injected into all pydantic-ai tools via RunContext.

    **LIFECYCLE**: This object is created FRESH for each request.
    - HTTP API: One instance per /chat request
    - Social: One instance per incoming message
    - CLI: One instance per user turn

    **ISOLATION**: Session-level data (e.g., tool_approval_policy) is
    NOT shared between users, chats, or requests. Each request gets
    an independent AgentDeps instance.

    **SECURITY**: Do NOT cache or reuse AgentDeps instances. Always call
    build_agent_deps() to create a fresh instance per request.
    """

    # --- Session identity ---
    chat_id: str = ""
    user_id: str = "default"

    # --- Sandbox / filesystem ---
    sandbox_enabled: bool = False
    workspace_root: str = ""
    custom_volumes: list = field(default_factory=list)
    path_resolver: Any = None  # PathResolver instance

    # --- Memory system ---
    memory_manager: Any = None  # MemoryManager instance

    # --- Social messaging ---
    channel_manager: Any = None  # ChannelManager instance
    event_loop: Optional[asyncio.AbstractEventLoop] = None
    social_context: dict = field(default_factory=dict)

    # --- Skills ---
    skill_manager: Any = None  # SkillManager instance

    # --- Human-in-the-loop (HITL) ---

    tool_approval_policy: dict = field(
        default_factory=dict
    )  # tool_name → "always_allow" | "always_deny"
    auto_approve_tools: bool = False
    cancel_event: Any = None  # asyncio.Event — set when stream is cancelled
    last_messages: Optional[list] = None  # To preserve session history correctly

    # --- A2UI canvas ---
    a2ui_queue: Optional[asyncio.Queue] = (
        None  # surface events queued by render_ui tool
    )
    inline_a2ui_surfaces: dict[str, dict[str, Any]] = field(default_factory=dict)
