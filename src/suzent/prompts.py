"""
Prompt formatting utilities for Suzent agents.

Provides functions to format and enhance agent instructions with dynamic context.
"""

from datetime import datetime

SUZENT_AGENT_INSTRUCTIONS = """
# Language Requirement
You should respond in the language of the user's query.

# Task Management
Make plans for complex tasks.

# Date Context
Today's date: {current_date}
"""


def format_instructions(base_instructions: str) -> str:
    """
    Format agent instructions by adding current date and other dynamic context.

    Args:
        base_instructions: The base instruction text

    Returns:
        Formatted instructions with date appended
    """
    current_date = datetime.now().strftime("%A, %B %d, %Y")
    suzent_instructions = SUZENT_AGENT_INSTRUCTIONS.format(current_date=current_date)
    return f"{suzent_instructions}\n\n{base_instructions}"
