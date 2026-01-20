"""
Prompt formatting utilities for Suzent agents.

Provides functions to format and enhance agent instructions with dynamic context.
"""

from datetime import datetime

SUZENT_AGENT_INSTRUCTIONS = """
# Role
You are Suzent, a digital coworker.

# Language Requirement
You should respond in the language of the user's query.

# Task Management
**MUST** make plans when a task requires:
- Multiple steps or tools.
- Information synthesis from several sources.
- Breaking down an ambiguous goal.

# Date Context
Today's date: {current_date}

# Base Instructions
{base_instructions}

{memory_context}
"""


def format_instructions(base_instructions: str, memory_context: str = "") -> str:
    """
    Format agent instructions by adding current date and other dynamic context.

    Args:
        base_instructions: The base instruction text

    Returns:
        Formatted instructions with date appended
    """
    current_date = datetime.now().strftime("%A, %B %d, %Y")
    suzent_instructions = SUZENT_AGENT_INSTRUCTIONS.format(
        current_date=current_date,
        base_instructions=base_instructions,
        memory_context=memory_context,
    )
    return suzent_instructions
