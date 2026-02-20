"""
Prompt formatting utilities for Suzent agents.

Provides functions to format and enhance agent instructions with dynamic context.
"""

from datetime import datetime

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

{custom_volumes_section}

{base_instructions_section}

{memory_context}

{social_context}
"""

CUSTOM_VOLUMES_SECTION = """# Custom Volumes
The following custom volumes are mounted and available:
{volumes_list}
"""

BASE_INSTRUCTIONS_SECTION = """# Base Instructions
{base_instructions}
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
) -> str:
    """
    Format agent instructions by adding current date, custom volumes, and other dynamic context.

    Args:
        base_instructions: The base instruction text
        memory_context: Context string from memory system
        custom_volumes: List of custom volume mount strings
        social_context: Pre-formatted social channel context string

    Returns:
        Formatted instructions with date and volumes appended
    """
    current_date = datetime.now().strftime("%A, %B %d, %Y")

    volumes_section = ""
    if custom_volumes:
        volumes_list = "\n".join([f"- {v}" for v in custom_volumes])
        volumes_section = CUSTOM_VOLUMES_SECTION.format(volumes_list=volumes_list)

    base_instructions_section = ""
    if base_instructions:
        base_instructions_section = BASE_INSTRUCTIONS_SECTION.format(
            base_instructions=base_instructions
        )

    suzent_instructions = SUZENT_AGENT_INSTRUCTIONS.format(
        current_date=current_date,
        custom_volumes_section=volumes_section,
        base_instructions_section=base_instructions_section,
        memory_context=memory_context,
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
