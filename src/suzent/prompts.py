"""
Prompt formatting utilities for Suzent agents.

Provides functions to format and enhance agent instructions with dynamic context.
"""

from datetime import datetime
import platform

SUZENT_AGENT_INSTRUCTIONS = """# Role
You are Suzent, a digital coworker.

# Language Requirement
You should respond in the language of the user's query.

# Task Management
**MUST** make todo plans when a task requires:
- Multiple steps or tools.
- Information synthesis from several sources.
- Breaking down an ambiguous goal into action items.

# Date Context
Today's date: {current_date}

{execution_mode_section}

{custom_volumes_section}

{base_instructions_section}

{memory_context}

{skills_context}

{social_context}
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
Env vars available: PERSISTENCE_PATH, SHARED_PATH, WORKSPACE_ROOT.
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
    "or things that need follow-up? If nothing needs attention, reply HEARTBEAT_OK."
)

HEARTBEAT_PROMPT_TEMPLATE = (
    "Background Heartbeat Check. Read the following instructions and follow them strictly. "
    "Do not infer or repeat old tasks from prior messages. "
    "If nothing needs attention or you have completed the check, reply EXACTLY with 'HEARTBEAT_OK'.\n\n"
    "---\n{instructions}\n---"
)

PLATFORM_CHAR_LIMITS = {
    "telegram": 4096,
    "slack": 40000,
    "discord": 2000,
    "feishu": 30000,
}


def format_instructions(
    base_instructions: str,
    memory_context: str = "",
    custom_volumes: list[str] = None,
    social_context: str = "",
    skills_context: str = "",
    sandbox_enabled: bool = False,
    workspace_root: str = "",
) -> str:
    """
    Format agent instructions by adding current date, execution mode, and other context.

    Args:
        base_instructions: The base instruction text
        memory_context: Context string from memory system
        custom_volumes: List of custom volume mount strings
        social_context: Pre-formatted social channel context string
        sandbox_enabled: Whether sandbox mode is active
        workspace_root: Root directory for host mode

    Returns:
        Formatted instructions with date and volumes appended
    """
    current_date = datetime.now().strftime("%A, %B %d, %Y")

    volumes_section = ""
    if custom_volumes:
        volumes_list = "\n".join(
            [f"- {v} (Host Path:Virtual Name)" for v in custom_volumes]
        )
        volumes_section = CUSTOM_VOLUMES_SECTION.format(volumes_list=volumes_list)

    execution_mode_section = ""
    if sandbox_enabled:
        execution_mode_section = EXECUTION_MODE_SECTION_SANDBOX
    else:
        execution_mode_section = EXECUTION_MODE_SECTION_HOST.format(
            workspace_root=workspace_root.replace("\\", "/"), os_name=platform.system()
        )

    base_instructions_section = ""
    if base_instructions:
        base_instructions_section = BASE_INSTRUCTIONS_SECTION.format(
            base_instructions=base_instructions
        )

    suzent_instructions = SUZENT_AGENT_INSTRUCTIONS.format(
        current_date=current_date,
        execution_mode_section=execution_mode_section,
        custom_volumes_section=volumes_section,
        base_instructions_section=base_instructions_section,
        memory_context=memory_context,
        skills_context=skills_context,
        social_context=social_context,
    )
    return suzent_instructions


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
