"""
Memory system prompt templates and context formatting.

Centralizes all prompt engineering for the memory system.
"""

from typing import Dict, List, Any, Optional


# ===== Core Memory Context Prompts =====


def format_core_memory_section(
    blocks: Dict[str, str],
    sandbox_enabled: bool = True,
    chat_id: Optional[str] = None,
    shared_path: Optional[str] = None,
    mount_skills: Optional[str] = None,
    mount_notebook: Optional[str] = None,
) -> str:
    """
    Format core memory blocks for agent context injection.

    Args:
        blocks: Dictionary of memory block labels to content
        sandbox_enabled: Whether sandbox mode is active
        chat_id: Current chat session ID (used to show the real context.md path)
        shared_path: Host path for /shared (non-sandbox mode only)
        mount_skills: Host path for /mnt/skills (non-sandbox mode only)
        mount_notebook: Host path for /mnt/notebook (non-sandbox mode only)

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

    # Build the real context.md path using the actual chat_id when available
    _ctx_segment = chat_id[:32] if chat_id else "{chat_id}"

    if sandbox_enabled:
        memory_workspace_title = "## Memory Workspace (/shared/memory/)"
        memory_files = (
            "- `/shared/memory/persona.md` — your identity, role, and workflow principles\n"
            "- `/shared/memory/user.md` — user preferences, tech stack, communication habits\n"
            "- `/shared/memory/MEMORY.md` — condensed long-term context and key decisions\n"
            f"- `/shared/memory/sessions/{_ctx_segment}/context.md` — **this session's** scratchpad and task state\n"
            "- `/shared/memory/archive/YYYY-MM-DD.md` — daily knowledge logs (auto-written, append-only)"
        )
        notebook_title = "## Notebook (/mnt/notebook/)"
        notebook_runbook = (
            "To run ingest: follow `/mnt/skills/notebook/ingest.md`\n"
            "To run lint: follow `/mnt/skills/notebook/lint.md`"
        )
        curated_memory_hint = "- Read `/shared/memory/MEMORY.md` for a curated summary of everything you know about the user"
    else:
        _shared = shared_path or "${SHARED_PATH}"
        _skills = mount_skills or "${MOUNT_SKILLS}"
        _notebook = mount_notebook
        memory_workspace_title = "## Memory Workspace (Host Paths)"
        memory_files = (
            f"- `{_shared}/memory/persona.md` — your identity, role, and workflow principles\n"
            f"- `{_shared}/memory/user.md` — user preferences, tech stack, communication habits\n"
            f"- `{_shared}/memory/MEMORY.md` — condensed long-term context and key decisions\n"
            f"- `{_shared}/memory/sessions/{_ctx_segment}/context.md` — **this session's** scratchpad and task state\n"
            f"- `{_shared}/memory/archive/YYYY-MM-DD.md` — daily knowledge logs (auto-written, append-only)"
        )
        notebook_title = "## Notebook (Host-Mounted Paths)"
        if _notebook:
            notebook_runbook = (
                f"To run ingest: follow `{_skills}/notebook/ingest.md`\n"
                f"To run lint: follow `{_skills}/notebook/lint.md`"
            )
        else:
            notebook_runbook = (
                f"To run ingest: follow `{_skills}/notebook/ingest.md`\n"
                f"To run lint: follow `{_skills}/notebook/lint.md`\n"
                "If notebook is not configured in this session, skip notebook operations."
            )
        curated_memory_hint = f"- Read `{_shared}/memory/MEMORY.md` for a curated summary of everything you know about the user"

    return f"""# Memory System

You operate under a **file-centric memory architecture** — markdown files are the single source of truth.

## Core Memory (Always Visible)
These files are loaded into your context at the start of every conversation:
{core_blocks_text}
## Archival Memory (Search When Needed)
A semantic vector index is built automatically from your memory files. Use `memory_search` to surface relevant past knowledge — especially useful for long-tail preferences and conversation history beyond the current session.

{memory_workspace_title}
Your memory lives in plain markdown files you can read and write directly:
{memory_files}

**How to update your memory:**
- To update persona, user profile, or long-term context: use `edit_file` or `write_file` on the corresponding `.md` file
- To update session scratchpad / task state: write to `context.md` in the sessions directory
- Do **not** append duplicate or ephemeral information; keep files concise and scannable

{notebook_title}
Your notebook IS the wiki. Pages live directly in the vault alongside your other notes —
no separate subfolder. You own this layer: create pages, update them, maintain cross-references,
and respect the existing vault structure.

Navigation:
- `index.md` - catalog of synthesized pages by category (at notebook root)
- `log.md` - append-only record of ingests, query filings, and lint passes (at notebook root)

**Before creating any page:** explore the vault with GlobTool to check whether a folder or
file already exists for that topic. If it does, link to it — do not duplicate it.

Query workflow:
1) Read `index.md` first to identify candidate pages
2) Read relevant pages and synthesize with citations
3) If the result is durable, file it back into the notebook

Durable outputs include comparisons, analyses, syntheses, and decision breakdowns.
When filing a durable output:
- Write a page in the appropriate vault location (not necessarily the root)
- Add it to `index.md`
- Append a `query-filed` entry to `log.md`

{notebook_runbook}

**Memory Guidelines:**
- Search archival memory before asking the user for information they may have already shared
- Write important new facts, decisions, and preferences to the appropriate memory file for durability
- Keep `context.md` as a live scratchpad: task breakdown, current goal, key constraints
{curated_memory_hint}
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

    return f"""<relevant_memories>
Here are relavant memories retrieved based on the user's query. 
Use these to inform your response, but do not feel obligated to include everything — prioritize relevance and importance.
{memories_text}
</relevant_memories>
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
Max 2000 words. Respond with the summary only.
"""
