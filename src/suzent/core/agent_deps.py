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
    """Dependencies injected into all pydantic-ai tools via RunContext."""

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
    sse_queue: Any = None  # asyncio.Queue — tools push approval requests here
    pending_approvals: dict = field(
        default_factory=dict
    )  # request_id → {event, approved, remember}
    tool_approval_policy: dict = field(
        default_factory=dict
    )  # tool_name → "always_allow" | "always_deny"
    cancel_event: Any = None  # asyncio.Event — set when stream is cancelled
