"""
Memory system prompt templates and context formatting.

Centralizes all prompt engineering for the memory system.
"""

from typing import Dict, List, Any


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

    return f"""## Memory System

You have access to a multi-tier memory system:

### Core Memory (Always Visible)
This is your active working memory. You can edit these blocks using the `memory_block_update` tool.
{core_blocks_text}
### Archival Memory (Search When Needed)
You have unlimited long-term memory storage that is automatically managed. Use `memory_search` to find relevant past information when needed.

### Memory Workspace (/shared/memory/)
Your memories are also persisted as plain markdown files that you can directly read and write:
- `/shared/memory/MEMORY.md` - Curated long-term memory (auto-updated from important facts)
- `/shared/memory/YYYY-MM-DD.md` - Daily logs with timestamped facts from conversations

You can read these files to review your memory history, or write to them to manually persist notes and observations.

**Memory Guidelines:**
- Update your core memory blocks when you learn important new information
- Search your archival memory before asking the user for information they may have already provided
- Core memory blocks are structured sections you can update; archival memory is automatically stored as you interact
- Use core memory for information you need to reference frequently; use archival memory for detailed historical context
- You can read `/shared/memory/MEMORY.md` for a curated summary of everything you know about the user
- Important decisions, preferences, and lasting facts should be written to memory for durability
"""


# ===== Phase 4: Improved Retrieval Formatting =====


def format_retrieved_memories_section(
    memories: List[Dict[str, Any]], tag_important: bool = True
) -> str:
    """
    Format retrieved memories for context injection.

    Kept lean — one line per memory so the agent can scan quickly.
    """
    import json as json_module

    if not memories:
        return ""

    lines = []

    for i, memory in enumerate(memories, 1):
        if isinstance(memory, str):
            lines.append(f"- {memory}")
            continue

        content = memory.get("content", "")
        importance = memory.get("importance", 0)

        metadata = memory.get("metadata", {})
        if isinstance(metadata, str):
            try:
                metadata = json_module.loads(metadata)
            except (json_module.JSONDecodeError, TypeError):
                metadata = {}
        metadata = metadata or {}

        # Single-line format: "- [category] content"
        category = metadata.get("category", "")
        prefix = f"[{category}] " if category else ""
        marker = "★ " if tag_important and importance > 0.7 else ""

        lines.append(f"- {marker}{prefix}{content}")

    memories_text = "\n".join(lines)

    return f"""<memory>
{memories_text}
</memory>
"""


# ===== Phase 3: Enhanced Fact Extraction Prompts =====

FACT_EXTRACTION_SYSTEM_PROMPT = """You are a memory extraction system. Write concise notes—not essays.

## What to Extract
- Personal info: name, location, profession, relationships
- Preferences: likes, dislikes, workflow habits
- Goals & projects: what they're working on, deadlines
- Technical context: stack, tools, skills
- Key decisions or outcomes

## Output Format

For each fact:
- **content**: One concise sentence. State the fact directly—no narration, no "User mentioned that..."
- **category**: One of [personal, preference, goal, context, technical, interaction]
- **importance**: 0.0-1.0 (0.8+ = critical, 0.5-0.8 = useful, <0.5 = minor)
- **tags**: 2-4 keywords
- **conversation_context**: { user_intent, agent_actions_summary, outcome } — keep each under 10 words

## Examples

### Good:
```json
{
  "content": "Building a React fintech dashboard; needs virtualization for 1000+ data points",
  "category": "technical",
  "importance": 0.8,
  "tags": ["react", "dashboard", "fintech"],
  "conversation_context": {
    "user_intent": "Optimize slow dashboard",
    "agent_actions_summary": "Recommended react-window",
    "outcome": "User plans to implement"
  }
}
```

```json
{
  "content": "Prefers dark mode for long coding sessions",
  "category": "preference",
  "importance": 0.6,
  "tags": ["dark-mode", "coding"],
  "conversation_context": {
    "user_intent": "Setting up editor",
    "agent_actions_summary": null,
    "outcome": "Noted preference"
  }
}
```

### Bad (too wordy):
```json
{
  "content": "User is building a React dashboard for their fintech company and asked about performance optimization. They mentioned the app loads slowly with 1000+ data points. Agent researched virtualization and recommended react-window library.",
  ...
}
```

## Rules
- One sentence per fact. No filler words.
- State facts directly: "Prefers X" not "User mentioned they prefer X"
- Skip greetings, ephemeral debugging, small talk
- Fewer high-quality facts > many low-quality ones
"""


def format_fact_extraction_user_prompt(content: str) -> str:
    """
    Format user prompt for fact extraction from a conversation turn.

    Args:
        content: The formatted conversation turn text (user message + assistant response + actions)

    Returns:
        Formatted extraction prompt
    """
    return f"""Extract memorable facts from this conversation turn. One concise sentence per fact.

---
{content}
---

Return valid JSON with a "facts" array. Skip if nothing worth remembering."""


# ===== Phase 5: Core Memory Summarization =====

CORE_MEMORY_SUMMARIZATION_PROMPT = """Condense these facts into a brief, scannable summary. Bullet points only. No prose.

{facts_list}

Group into sections (omit if empty): **Profile**, **Preferences**, **Stack**, **Constraints**.
Max 200 words. Respond with the summary only.
"""
