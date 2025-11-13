"""
Memory system prompt templates and context formatting.

Centralizes all prompt engineering for the memory system.
"""

from typing import Dict, Optional


# ===== Core Memory Context Prompts =====

def format_core_memory_section(blocks: Dict[str, str]) -> str:
    """
    Format core memory blocks for agent context injection.
    
    Args:
        blocks: Dictionary of memory block labels to content
        
    Returns:
        Formatted string for prompt injection
    """
    return f"""
## Your Memory System

You have access to a two-tier memory system:

### Core Memory (Always Visible)
This is your active working memory. You can edit these blocks using the `memory_block_update` tool.

**Persona** (your identity and capabilities):
{blocks.get('persona', 'Not set')}

**User** (information about the current user):
{blocks.get('user', 'Not set')}

**Facts** (key facts you should always remember):
{blocks.get('facts', 'Not set')}

**Context** (current session context):
{blocks.get('context', 'Not set')}

### Archival Memory (Search When Needed)
You have unlimited long-term memory storage that is automatically managed. Use `memory_search` to find relevant past information when needed.

**Memory Guidelines:**
- Update your core memory blocks when you learn important new information about yourself or the user
- Search your archival memory before asking the user for information they may have already provided
- Memories are automatically stored as you interact—you don't need to explicitly save them
"""


def format_retrieved_memories_section(memories: list, tag_important: bool = True) -> str:
    """
    Format retrieved memories for context injection.
    
    Args:
        memories: List of memory dictionaries with content, importance, timestamp
        tag_important: Whether to tag high-importance memories
        
    Returns:
        Formatted string with relevant memories
    """
    if not memories:
        return ""
    
    memory_context = "\n## Relevant Memories\n\n"
    memory_context += "Based on your query, here are relevant memories from past conversations:\n\n"
    
    for i, memory in enumerate(memories, 1):
        content = memory.get('content', '')
        importance = memory.get('importance', 0)
        
        memory_context += f"{i}. {content}"
        if tag_important and importance > 0.7:
            memory_context += " [Important]"
        memory_context += "\n"
    
    memory_context += "\n"
    return memory_context


# ===== Fact Extraction Prompts =====

FACT_EXTRACTION_SYSTEM_PROMPT = """You are a fact extraction system. Extract memorable facts from user messages.

Focus on extracting:
- Personal information (name, location, job, etc.)
- Preferences (likes, dislikes, favorites)
- Goals and intentions (plans, desires, tasks)
- Important context (relationships, events, experiences)
- Technical details (tools they use, skills they have)

For each fact, provide:
- content: The fact as a clear, standalone statement
- category: One of [personal, preference, goal, context, technical, other]
- importance: Float 0.0-1.0 (0.8-1.0 = critical, 0.5-0.8 = important, 0.0-0.5 = minor)
- tags: List of relevant tags

Return JSON in this format:
{
  "facts": [
    {
      "content": "User prefers dark mode",
      "category": "preference",
      "importance": 0.7,
      "tags": ["preference", "ui"]
    }
  ]
}

If no facts are worth extracting, return {"facts": []}."""


def format_fact_extraction_user_prompt(content: str) -> str:
    """
    Format user prompt for fact extraction.
    
    Args:
        content: User message content
        
    Returns:
        Formatted extraction prompt
    """
    return f"""Extract facts from this message:

{content}

Remember: Only extract facts that are worth remembering long-term. Skip questions, greetings, and ephemeral content."""
