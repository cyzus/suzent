"""
Memory system prompt templates and context formatting.

Centralizes all prompt engineering for the memory system.
"""

from typing import Dict, List, Any
from datetime import datetime


# ===== Core Memory Context Prompts =====


def format_core_memory_section(blocks: Dict[str, str]) -> str:
    """
    Format core memory blocks for agent context injection.

    Args:
        blocks: Dictionary of memory block labels to content

    Returns:
        Formatted string for prompt injection
    """
    # Format core memory blocks dynamically
    core_blocks_text = ""
    if blocks:
        for label, content in blocks.items():
            core_blocks_text += f"\n**{label.capitalize()}**:\n{content or 'Not set'}\n"
    else:
        core_blocks_text = "\nNo core memory blocks configured.\n"

    return f"""
## Memory System

You have access to a two-tier memory system:

### Core Memory (Always Visible)
This is your active working memory. You can edit these blocks using the `memory_block_update` tool.
{core_blocks_text}
### Archival Memory (Search When Needed)
You have unlimited long-term memory storage that is automatically managed. Use `memory_search` to find relevant past information when needed.

**Memory Guidelines:**
- Update your core memory blocks when you learn important new information
- Search your archival memory before asking the user for information they may have already provided
- Core memory blocks are structured sections you can update; archival memory is automatically stored as you interact
- Use core memory for information you need to reference frequently; use archival memory for detailed historical context
"""


# ===== Phase 4: Improved Retrieval Formatting =====


def format_retrieved_memories_section(
    memories: List[Dict[str, Any]], tag_important: bool = True
) -> str:
    """
    Format retrieved memories for context injection with rich context.

    Args:
        memories: List of memory dictionaries with content, importance, timestamp, metadata
        tag_important: Whether to tag high-importance memories

    Returns:
        Formatted string with relevant memories and their context
    """
    import json as json_module

    if not memories:
        return ""

    formatted_memories = []

    for i, memory in enumerate(memories, 1):
        # Handle case where memory might be a string (shouldn't happen but defensive)
        if isinstance(memory, str):
            formatted_memories.append(f"{i}. {memory}")
            continue

        content = memory.get("content", "")
        importance = memory.get("importance", 0)
        updated_at = memory.get("updated_at")

        # Parse metadata - it might be a JSON string from PostgreSQL
        metadata = memory.get("metadata", {})
        if isinstance(metadata, str):
            try:
                metadata = json_module.loads(metadata)
            except (json_module.JSONDecodeError, TypeError):
                metadata = {}
        metadata = metadata or {}

        # Build the memory entry
        entry_parts = []

        # Header with importance tag
        header = f"{i}."
        if tag_important and importance > 0.7:
            header += " **[Important]**"

        # Category if available
        category = metadata.get("category")
        if category:
            header += f" [{category.capitalize()}]"

        entry_parts.append(header)

        # Main content (indented)
        entry_parts.append(f"   {content}")

        # Conversation context if available (Phase 4 enhancement)
        conversation_context = metadata.get("conversation_context")
        if conversation_context:
            context_lines = []

            user_intent = conversation_context.get("user_intent")
            if user_intent and user_intent != "inferred from conversation":
                context_lines.append(f"Context: {user_intent}")

            agent_actions = conversation_context.get("agent_actions_summary")
            if agent_actions:
                context_lines.append(f"Actions taken: {agent_actions}")

            outcome = conversation_context.get("outcome")
            if outcome and outcome != "extracted from conversation turn":
                context_lines.append(f"Outcome: {outcome}")

            if context_lines:
                entry_parts.append("   " + " | ".join(context_lines))

        # Tags if available
        tags = metadata.get("tags", [])
        if tags:
            entry_parts.append(f"   Tags: {', '.join(tags)}")

        # Timestamp
        if updated_at:
            if isinstance(updated_at, datetime):
                time_str = updated_at.strftime("%Y-%m-%d %H:%M")
            else:
                time_str = str(updated_at)
            entry_parts.append(f"   (Updated: {time_str})")

        formatted_memories.append("\n".join(entry_parts))

    memories_text = "\n\n".join(formatted_memories)

    return f"""
<memory>
Based on the user's query, here are relevant memories from past conversations:

{memories_text}

Use these memories to provide context-aware responses. If the user hasn't explicitly asked about these topics, use them subtly to personalize your response without overwhelming them.
</memory>
"""


# ===== Phase 3: Enhanced Fact Extraction Prompts =====

FACT_EXTRACTION_SYSTEM_PROMPT = """You are a memory extraction system that captures rich, contextual information from conversations.

Your goal is to extract memorable information that will be useful for future interactions. Focus on quality over quantity - only extract information that provides lasting value.

## What to Extract

1. **Personal Information**: Name, location, profession, relationships, living situation
2. **Preferences**: Likes, dislikes, favorites, style preferences, workflow preferences
3. **Goals & Projects**: Current projects, future plans, aspirations, deadlines
4. **Technical Context**: Tools used, tech stack, skills, expertise areas
5. **Important Context**: Key decisions made, problems solved, patterns observed

## Output Format

For each extracted fact, provide:
- **content**: A rich, standalone summary (2-4 sentences) that captures:
  * What information was shared
  * The context or situation when it came up
  * Any relevant nuances or details
- **category**: One of [personal, preference, goal, context, technical, interaction]
- **importance**: Float 0.0-1.0
  * 0.8-1.0: Critical (identity, major decisions, recurring themes)
  * 0.5-0.8: Important (preferences, active projects, useful context)
  * 0.0-0.5: Minor (passing mentions, temporary context)
- **tags**: Relevant keywords for search (aim for 3-5 tags)
- **conversation_context**: Object with:
  * user_intent: What the user was trying to accomplish
  * agent_actions_summary: What actions/tools the agent used (if any)
  * outcome: Result of the interaction

## Examples

### Good (Rich Context):
```json
{
  "content": "User is building a React dashboard for their fintech company and asked about performance optimization. They mentioned the app loads slowly with 1000+ data points. Agent researched virtualization and recommended react-window library.",
  "category": "technical",
  "importance": 0.8,
  "tags": ["react", "performance", "virtualization", "dashboard", "fintech"],
  "conversation_context": {
    "user_intent": "Optimize slow-loading dashboard with many data points",
    "agent_actions_summary": "Searched for React virtualization libraries",
    "outcome": "Recommended react-window, user plans to implement"
  }
}
```

### Bad (Too Minimal):
```json
{
  "content": "User uses React",
  "category": "technical",
  "importance": 0.5,
  "tags": ["react"]
}
```

## Guidelines

- **Be Specific**: "User prefers dark mode to reduce eye strain during long coding sessions" is better than "User prefers dark mode"
- **Include Why**: Capture the reasoning behind preferences or decisions when available
- **Capture Patterns**: If something comes up repeatedly, note that pattern
- **Skip Ephemeral Content**: Don't extract greetings, questions without context, or one-time debugging sessions
- **Focus on Actionable**: Prefer facts that could influence future interactions
"""


def format_fact_extraction_user_prompt(content: str) -> str:
    """
    Format user prompt for fact extraction from a conversation turn.

    Args:
        content: The formatted conversation turn text (user message + assistant response + actions)

    Returns:
        Formatted extraction prompt
    """
    return f"""Analyze this conversation turn and extract any memorable facts:

---
{content}
---

Remember:
- Extract facts that provide lasting value for future interactions
- Include rich context, not just bare facts
- Capture the "why" behind preferences and decisions
- Skip ephemeral content (pure questions, greetings, one-time debugging)
- If the assistant used tools or took actions, note what was done and the outcome

Return your response as valid JSON with a "facts" array."""


# ===== Legacy Support =====


def format_fact_extraction_user_prompt_simple(content: str) -> str:
    """
    Legacy simple format for extracting facts from just a user message.
    Kept for backward compatibility.

    Args:
        content: User message content

    Returns:
        Formatted extraction prompt
    """
    return f"""Extract facts from this user message:

{content}

Remember: Only extract facts that are worth remembering long-term. Skip questions, greetings, and ephemeral content."""


# ===== Phase 5: Core Memory Summarization =====

CORE_MEMORY_SUMMARIZATION_PROMPT = """You are an expert memory organizer.

Your task is to synthesize a list of important isolated facts into a concise, coherent "Facts" summary for the AI's core memory.
This summary will be always visible to the AI, so it must be highly dense and relevant.

## Input Facts
{facts_list}

## Instructions
1. Group related facts (e.g., Personal, Technical, Preferences).
2. Remove duplicates and merge related information.
3. Prioritize high-importance facts.
4. Write in a clear, objective style.
5. Limit the output to roughly 500 words maximum.
6. Use bullet points for readability.

## Output Format
Create a structured summary with these sections (omit if empty):
- **User Profile**: Key personal details and goals.
- **Preferences**: Important likes/dislikes/workflow preferences.
- **Technical Context**: Tech stack, tools, and skills.
- **Key Constraints**: Deadlines, budget, or other hard constraints.

Respond ONLY with the summary text.
"""
