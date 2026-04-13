"""
Prompt formatting utilities for Suzent agents.

Provides functions to format and enhance agent instructions with dynamic context.
"""

from datetime import datetime
import platform
from typing import Any, Callable

STATIC_INSTRUCTIONS = """# Role
You are Suzent, a digital coworker.

# Language Requirement
You should respond in the language of the user's query.

# Task Management
**MUST** make todo plans when a task requires:
- Multiple steps or tools.
- Information synthesis from several sources.
- Breaking down an ambiguous goal into action items.

# Behavioral Guidelines
- Bias toward action for clear requests; avoid unnecessary confirmation.
- Do not add improvements beyond what the user asked.
- Diagnose failures before retrying a different approach.
- Verify important outcomes before claiming completion.
- Report outcomes honestly. If checks fail, report the exact failure.

# Tool Usage Safety
- Prefer dedicated tools for file operations over shell shortcuts.
- Ask for confirmation before destructive or hard-to-reverse actions (e.g., deleting data, force push, reset --hard).
"""

CUSTOM_VOLUMES_SECTION = """# Directory Mappings
The following directories are mapped and available for your use:
{volumes_list}
"""

EXECUTION_MODE_SECTION_SANDBOX = """# Environment: Sandbox
You are in a sandbox environment. Use virtual paths (e.g., `/persistence`, `/mnt/...`). Host paths are inaccessible.
"""

EXECUTION_MODE_SECTION_HOST = """# Environment: Host
You are on the host machine ({os_name}). Use host paths (e.g., `{workspace_root}`).
Do NOT use virtual `/mnt/...` paths.
Env vars available: PERSISTENCE_PATH, SHARED_PATH, WORKSPACE_ROOT, and MOUNT_* for mapped volumes.
"""

BASE_INSTRUCTIONS_SECTION = """# Base Instructions
{base_instructions}
"""

SKILLS_CONTEXT_SECTION = """# Available Skills
You have a SkillTool that loads specialized knowledge. Use it IMMEDIATELY when the user's task matches a skill.

{skills_xml}
"""

SOCIAL_CONTEXT_SECTION = """# Social Channel Context
You are responding to messages from a social messaging platform ({platform}).
Each incoming message is prefixed with a header in this format:
  [{platform_title} <sender_name> id:<sender_id>]
This tells you who sent the message, on which platform, and their platform user ID.

Current conversation: {sender_name} on {platform} (message limit: {char_limit} chars).

## SocialMessageTool
You have the SocialMessageTool available for sending messages to social channels.
- Use it to send progress updates while working (e.g. "Looking into that for you...")
- Your final answer is also automatically delivered — the tool is for intermediate updates
- Keep messages concise and chat-appropriate for the platform
"""


HEARTBEAT_BASE_INSTRUCTIONS = (
    "Check in on this session. Are there any open tasks, pending questions, "
    "or things that need follow-up?"
)

HEARTBEAT_PROMPT_TEMPLATE = (
    "Background Heartbeat Check. Read the following instructions and follow them strictly. "
    "Do not infer or repeat old tasks from prior messages. "
    "Reply EXACTLY with 'HEARTBEAT_OK' if nothing needs attention."
    "Otherwise, report what needs attention or what tasks you have completed. \n\n"
    "---\n{instructions}\n---"
)

PLATFORM_CHAR_LIMITS = {
    "telegram": 4096,
    "slack": 40000,
    "discord": 2000,
    "feishu": 30000,
}

_PROMPT_SECTION_CACHE: dict[str, str] = {}


def resolve_prompt_section(
    name: str,
    compute: Callable[[], str],
    *,
    cache_break: bool = False,
) -> str:
    """Resolve a prompt section value with optional cache bypass.

    This is a lightweight interface mirroring section-level cache-break
    semantics so callers can opt in incrementally.
    """
    if not cache_break and name in _PROMPT_SECTION_CACHE:
        return _PROMPT_SECTION_CACHE[name]

    value = compute()
    _PROMPT_SECTION_CACHE[name] = value
    return value


def clear_prompt_section_cache() -> None:
    """Clear in-process prompt section cache."""
    _PROMPT_SECTION_CACHE.clear()


def build_execution_mode_section(
    sandbox_enabled: bool, workspace_root: str = ""
) -> str:
    """Build environment mode section for host or sandbox execution."""
    if sandbox_enabled:
        return EXECUTION_MODE_SECTION_SANDBOX

    return EXECUTION_MODE_SECTION_HOST.format(
        workspace_root=workspace_root.replace("\\", "/"), os_name=platform.system()
    )


def build_custom_volumes_section(custom_volumes: list[str] | None = None) -> str:
    """Build directory mapping section for configured custom volumes."""
    if not custom_volumes:
        return ""

    volumes_list = "\n".join(
        [f"- {v} (Host Path:Virtual Name)" for v in custom_volumes]
    )
    return CUSTOM_VOLUMES_SECTION.format(volumes_list=volumes_list)


def build_base_instructions_section(base_instructions: str = "") -> str:
    """Build optional user-configured instruction section."""
    if not base_instructions:
        return ""
    return BASE_INSTRUCTIONS_SECTION.format(base_instructions=base_instructions)


def build_session_guidance_section(session_guidance_items: list[str] | None) -> str:
    """Build dynamic session guidance from tool-provided metadata."""
    if not session_guidance_items:
        return ""

    bullet_items = "\n".join([f"- {item}" for item in session_guidance_items])
    return f"# Session Guidance\n{bullet_items}"


def register_dynamic_instructions(
    agent: Any,
    *,
    base_instructions: str,
    memory_context: str | None,
    session_guidance_items: list[str] | None = None,
) -> None:
    """Register runtime dynamic instruction providers on the given agent."""

    @agent.instructions
    def inject_date_context(_: Any) -> str:
        return (
            f"# Date Context\nToday's date: {datetime.now().strftime('%A, %B %d, %Y')}"
        )

    @agent.instructions
    def inject_environment_context(ctx: Any) -> str:
        return build_execution_mode_section(
            sandbox_enabled=ctx.deps.sandbox_enabled,
            workspace_root=ctx.deps.workspace_root,
        )

    @agent.instructions
    def inject_volumes_context(ctx: Any) -> str:
        return build_custom_volumes_section(ctx.deps.custom_volumes)

    @agent.instructions
    def inject_base_instructions(_: Any) -> str:
        return resolve_prompt_section(
            "base_instructions",
            lambda: build_base_instructions_section(base_instructions),
        )

    @agent.instructions
    def inject_session_guidance(_: Any) -> str:
        return resolve_prompt_section(
            "session_guidance",
            lambda: build_session_guidance_section(session_guidance_items),
        )

    @agent.instructions
    def inject_memory_context(_: Any) -> str:
        return memory_context or ""

    @agent.instructions
    def inject_skills_context(ctx: Any) -> str:
        skill_mgr = ctx.deps.skill_manager
        if not skill_mgr or not skill_mgr.enabled_skills:
            return ""

        return SKILLS_CONTEXT_SECTION.format(
            skills_xml=skill_mgr.get_skills_xml(
                sandbox_enabled=ctx.deps.sandbox_enabled
            )
        )

    @agent.instructions
    def inject_social_context(ctx: Any) -> str:
        if not ctx.deps.social_context:
            return ""
        return build_social_context(ctx.deps.social_context)


def build_social_context(social_ctx: dict) -> str:
    """
    Build the social context string from a social context dict.

    Args:
        social_ctx: Dict with keys: platform, sender_name, sender_id, target_id

    Returns:
        Formatted social context section string.
    """
    platform = social_ctx.get("platform", "unknown")
    sender_name = social_ctx.get("sender_name", "User")
    char_limit = PLATFORM_CHAR_LIMITS.get(platform, 4096)

    return SOCIAL_CONTEXT_SECTION.format(
        sender_name=sender_name,
        platform=platform,
        platform_title=platform.title(),
        char_limit=char_limit,
    )
