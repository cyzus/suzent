"""
Memory system prompt templates and context formatting.

Centralizes all prompt engineering for the memory system.
"""

from typing import Dict, List, Any, Optional

from suzent.memory.markdown_store import MEMORY_GENERATED_END


# ===== Core Memory Context Prompts =====


def _notebook_hint(title: str, root: str, skill_available: bool) -> str:
    """Point at wherever the vault conventions can actually be reached.

    Skills are disabled by default, so `SkillTool` is often not equipped. Naming
    a skill the model cannot load would be worse than saying nothing — it looks
    like a route out of the problem and is not one. In that case point at the
    vault's own `schema.md`, which the skill itself treats as the sole authority
    anyway, so the fallback is the same source without the tool in between.
    """
    if skill_available:
        return (
            f"{title}\n"
            "Load the `notebook` skill before any vault work. It owns the vault "
            "conventions, the ingest and lint runbooks, and the rules for when a "
            "result may be filed."
        )
    return (
        f"{title}\n"
        f"Read `{root}/schema.md` before any vault work — it is the authority on "
        "structure, naming, indexes and cross-links. Check for an existing page "
        "before creating one, and file a result only when asked to."
    )


def format_core_memory_section(
    blocks: Dict[str, str],
    sandbox_enabled: bool = True,
    chat_id: Optional[str] = None,
    shared_path: Optional[str] = None,
    mount_skills: Optional[str] = None,
    mount_notebook: Optional[str] = None,
    project_context_path: Optional[str] = None,
    notebook_skill_available: bool = True,
) -> str:
    """
    Format core memory blocks for agent context injection.

    Args:
        blocks: Dictionary of memory block labels to content
        sandbox_enabled: Whether sandbox mode is active
        chat_id: Retained for backwards-compatible callers.
        shared_path: Host path for /shared (non-sandbox mode only)
        mount_skills: Deprecated; skill locations come from the active skill catalog.
        mount_notebook: Host path for /mnt/notebook (non-sandbox mode only)
        project_context_path: Visible path to the project-scoped context.md file.

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

    if sandbox_enabled:
        _context_path = project_context_path or "/workspace/context.md"
        memory_workspace_title = "## Memory Workspace (/shared/memory/)"
        memory_files = (
            "- `/shared/memory/persona.md` — your identity, role, and workflow principles\n"
            "- `/shared/memory/user.md` — user preferences, tech stack, communication habits\n"
            "- `/shared/memory/MEMORY.md` — condensed long-term context and key decisions\n"
            f"- `{_context_path}` — **this project's** shared scratchpad and task state\n"
            "- `/shared/memory/archive/YYYY-MM-DD.md` — daily knowledge logs (auto-written, append-only)"
        )
        notebook_hint = _notebook_hint(
            "## Notebook (/mnt/notebook/)", "/mnt/notebook", notebook_skill_available
        )
        curated_memory_hint = "- Read `/shared/memory/MEMORY.md` for a curated summary of everything you know about the user"
    else:
        _shared = shared_path or "${SHARED_PATH}"
        _notebook = mount_notebook
        _context_path = project_context_path or "${PROJECT_PATH}/context.md"
        memory_workspace_title = "## Memory Workspace (Host Paths)"
        memory_files = (
            f"- `{_shared}/memory/persona.md` — your identity, role, and workflow principles\n"
            f"- `{_shared}/memory/user.md` — user preferences, tech stack, communication habits\n"
            f"- `{_shared}/memory/MEMORY.md` — condensed long-term context and key decisions\n"
            f"- `{_context_path}` — **this project's** shared scratchpad and task state\n"
            f"- `{_shared}/memory/archive/YYYY-MM-DD.md` — daily knowledge logs (auto-written, append-only)"
        )
        notebook_hint = _notebook_hint(
            "## Notebook (Host-Mounted Paths)", _notebook, notebook_skill_available
        )
        if not _notebook:
            notebook_hint = (
                "## Notebook\n"
                "No notebook is configured in this session; skip notebook operations."
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
- To update shared project context and task state: write to the project's `context.md`
- `MEMORY.md` is part generated: consolidation rewrites everything above the
  `{MEMORY_GENERATED_END}` marker, so put anything you want to keep **below** it. Text
  above that line is not yours and will not survive the next pass
- Do **not** append duplicate or ephemeral information; keep files concise and scannable

{notebook_hint}

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

## Already-known facts
The prompt may list facts already in memory. They are context, not material:

- Do NOT re-extract one because it came up again. Stable facts (someone's name, how
  they like to be addressed, a long-running project) surface constantly; re-stating
  them is what fills memory with duplicates.
- DO extract when the turn CHANGES a known fact — new specifics, a correction, a
  reversal. Write the full updated fact, not the delta, and lead with what changed.
- A near-repeat that adds nothing is not a change. "Wants water reminders" after
  "Wants water reminders hourly 9am-9pm" is a step backwards; skip it.
- When in doubt about a fact that carries NEW information, extract it. Losing an
  update is worse than storing a duplicate.
"""


def format_known_facts_block(known_facts: Optional[List[str]]) -> str:
    """Render already-known facts for the extraction prompt, or "" if there are none.

    Extraction is otherwise blind: it sees one conversation turn and no memory, so
    every mention of a stable fact reads as new. Showing what is already stored is
    what lets the model tell a repeat from an update.
    """
    if not known_facts:
        return ""
    lines = "\n".join(f"- {f}" for f in known_facts)
    return f"""## Already in memory
{lines}

Do not re-extract these. Extract only what is new, or what CHANGES one of them.

"""


def format_fact_extraction_user_prompt(
    content: str, known_facts: Optional[List[str]] = None
) -> str:
    """
    Format user prompt for fact extraction from a conversation turn.

    Args:
        content: The formatted conversation turn text (user message + assistant response + actions)
        known_facts: Facts already in memory, nearest-first. Omitted when retrieval
            is unavailable — extraction then behaves exactly as it did before.

    Returns:
        Formatted extraction prompt
    """
    return f"""Extract memorable facts from this conversation turn. One concise sentence per fact.

{format_known_facts_block(known_facts)}---
{content}
---

Return valid JSON with a "facts" array. Skip if nothing worth remembering."""


# ===== Phase 5: Core Memory Summarization =====

CORE_MEMORY_SUMMARIZATION_PROMPT = """Condense these facts into a brief, scannable summary. Bullet points only. No prose.

{facts_list}

Group into sections (omit if empty): **Profile**, **Preferences**, **Stack**, **Constraints**.
Max 2000 words. Respond with the summary only.
"""


# ===== Dream consolidation (autonomous wiki keeper) =====

# Virtual roots used in the dream/lint prompts. PathResolver maps these in BOTH
# sandbox and host mode, so the agent's file tools resolve them regardless of mode.
# Centralized here so the paths live in one place rather than scattered across the
# prompt strings below.
DREAM_MEMORY_ROOT = "/shared/memory"  # daily logs: {DREAM_MEMORY_ROOT}/archive/*.md
DREAM_NOTEBOOK_ROOT = "/mnt/notebook"  # the vault the agent maintains

# Where the dream drops fact lines it has folded into the vault and wants dropped
# from the search index. The agent only ever writes this file; the runner turns the
# lines into tombstones and reindexes the affected logs, keeping index mutation out
# of the agent's hands and the daily logs append-only.
DREAM_SUPERSEDED_FILENAME = "superseded.txt"
DREAM_SUPERSEDED_PATH = f"{DREAM_NOTEBOOK_ROOT}/.state/{DREAM_SUPERSEDED_FILENAME}"

DREAM_SYSTEM_PROMPT = f"""You are Suzent's memory consolidation agent ("dream"). You run \
autonomously to turn the raw, append-only daily memory logs into a clean, durable, \
cross-referenced knowledge vault.

Tools: read_file, write_file, edit_file, glob_search, grep_search, memory_search.
Filesystem:
- Daily logs (READ-ONLY source): {DREAM_MEMORY_ROOT}/archive/YYYY-MM-DD.md  — NEVER edit or delete these.
- The vault (your workspace):     {DREAM_NOTEBOOK_ROOT}/  — schema.md, index.md, log.md, zoned pages.

Rules:
- ALWAYS read {DREAM_NOTEBOOK_ROOT}/schema.md first; follow its zones, naming, and frontmatter exactly.
- Improve existing pages; never create near-duplicates. Search before you write.
- Preserve history: when a fact changes over time, record "currently X; previously Y" — never silently overwrite.
- Only remove a statement when it is a genuine correction or an exact duplicate.
- Do NOT write to log.md — the runner records consolidation events there. Put conflicts on content pages.
- {DREAM_SUPERSEDED_PATH} is append-only and write-only for you: read it if you must, never clear it.
"""

DREAM_INSTRUCTIONS = f"""Consolidate the daily memory logs dated after {{start}} through {{end}} into the vault.

1. Orient: read schema.md and index.md; glob_search {DREAM_NOTEBOOK_ROOT} for existing pages.
2. Read the logs: {DREAM_MEMORY_ROOT}/archive/*.md dated after {{start}} through {{end}}.
3. For each distinct fact/topic:
   a. Find the page it belongs to (index.md + glob_search/grep_search + memory_search).
      Personal facts about the user -> 3_Personal/ ; domain knowledge -> 2_Wiki/.
   b. Apply the matching case:
      - Duplicate (same fact reworded)              -> confirm, do not restate. Bump the
                                                       claim's confirmation marker
                                                       (step 3e), replace the bullet text
                                                       only if the new wording is MORE
                                                       specific, then retire the log lines
                                                       (step 3d). Never add a second
                                                       bullet, and never let a vaguer
                                                       restatement overwrite a detailed
                                                       claim you already hold.
      - New, non-conflicting                        -> add under the right section.
      - Correction (new entry shows old was wrong)  -> replace the wrong statement.
      - Change over time (both true at diff. times) -> rewrite as "Currently X (since {{end}});
                                                       previously Y." Apply the schema's lifecycle fields.
      - Genuine conflict you can't confidently resolve -> keep the more recent claim, add a
        `> [!warning] Conflicting claims: <A> vs <B> (<dates>)` callout on the relevant
        content page (or create a conflict-review page in the schema's appropriate location
        if no topical page exists) and apply the schema's needs-review marker.
   c. Convert relative dates ("yesterday") to absolute.
   d. Retire what you folded in: append the exact log fact text (the part after the
      `- [category] ` prefix, without the trailing backtick tags) to
      {DREAM_SUPERSEDED_PATH}, one per line, for any line that is now fully represented
      on a page AND adds nothing the page does not say. The runner drops those from the
      search index; the daily logs themselves stay untouched. When in doubt, leave it
      out — a duplicate in the index is cheaper than a fact that vanishes.
   e. Lifecycle on {DREAM_NOTEBOOK_ROOT}/3_Personal/ pages, whether or not this vault's
      schema.md mentions it (older vaults were seeded before these rules existed):
      - A repeated claim gets a marker on its bullet: `(confirmed 12x, last YYYY-MM-DD)`.
        Absent marker means confirmed once. Increment it and set the date; a claim the user
        keeps repeating is one claim confirmed many times, not many claims.
      - A repeat that CONTRADICTS the bullet is a correction, not a confirmation — reset the
        count and apply the correction case above.
      - Give each page a `stale_after` derived from the fact category: identity none,
        preference 1 year, technical 6 months, goal 3 months, context 3 weeks.
4. Confirmations recorded by the write path since the last consolidation. These were
   said again word-for-word and deliberately NOT written to a daily log, so this list
   is the only record that they recurred. For each, find the claim on its page and bump
   its marker by the count shown (step 3e); do not add a bullet, and do not treat one
   as a correction — a contradicting restatement never reaches this list.
{{confirmations}}
5. Claims due for a revisit. Re-confirm each against the logs you just read: if it is
   supported, refresh the date; if it is contradicted, apply the correction case; if the
   logs say nothing either way, leave it and let lint decide. Never delete here.
   A page listed as `stale_after unset` predates the rule and has no expiry at all: give
   it one from step 3's category table while you are there, whatever the logs say.
{{revisits}}
6. Add `## Related` links using the schema's link style.
7. Update index.md. Do NOT write the watermark to log.md — the runner records it.

Return a one-paragraph summary of what you created, updated, superseded, or flagged.
"""


def format_confirmations_block(rows: Optional[List[dict]]) -> str:
    """Render the confirmations sidecar for the dream prompt.

    `rows` is `markdown_store.summarize_confirmations()` output: one entry per claim
    with a count and the last date it was restated.
    """
    if not rows:
        return "   (none pending)"
    lines = []
    for row in rows:
        content = " ".join(str(row.get("content", "")).split())
        if not content:
            continue
        lines.append(
            f"   - {content} — +{row.get('count', 1)}x, last {row.get('last')}"
        )
    return "\n".join(lines) or "   (none pending)"


def format_revisits_block(rows: Optional[List[dict]]) -> str:
    """Render the revisit queue: vault pages whose `stale_after` has passed."""
    if not rows:
        return "   (none due)"
    return "\n".join(
        f"   - {row['page']} (stale_after {row['stale_after']})" for row in rows
    )


# ---- Lint phase: periodic editorial audit of the vault (runs after ingest catches up) ----

LINT_SYSTEM_PROMPT = f"""You are Suzent's memory consolidation agent ("dream"), running your \
periodic LINT pass: an editorial health-check of the notebook vault. You do NOT ingest new daily \
logs here — you audit and repair what already exists so the knowledge graph stays consistent and \
does not silently decay.

Tools: read_file, write_file, edit_file, glob_search, grep_search, memory_search.
Filesystem:
- The vault (your workspace): {DREAM_NOTEBOOK_ROOT}/  — schema.md, index.md, log.md, zoned pages.

Rules:
- ALWAYS read {DREAM_NOTEBOOK_ROOT}/schema.md first; follow its zones, naming, and frontmatter exactly.
- Repair conservatively. Fix links/structure freely; only delete a page if it is truly obsolete.
- Never fabricate facts. When a contradiction needs human judgement, FLAG it, do not guess.
- Do NOT write the lint log entry to log.md — the runner records that. Put callouts on content pages.
"""

LINT_INSTRUCTIONS = f"""Run an editorial lint pass over the notebook vault.

1. Orient: read schema.md and index.md; glob_search {DREAM_NOTEBOOK_ROOT} for ALL pages (many live outside index.md).
2. Contradictions: read related pages; where claims conflict, resolve with the better-supported/more
   recent claim. If it needs human judgement, add a `> [!warning] Contradiction: <desc>` callout on the
   page AND prepend a `> [!alert] Contradiction found in <schema-compliant link>` line near the top of index.md.
3. Hierarchy: ensure entity/detail pages link up to their parent category; connect micro-islands to a
   higher-level concept or index so nothing is stranded.
4. Broken links: for each index.md entry verify the file exists (fix/remove stale ones). Repair internal
   links according to the schema.
5. Orphans: a page not in index.md and not linked anywhere — add to index.md if valuable, link it from a
   related page, or delete only if truly obsolete.
6. Reciprocal links: if A links B in `## Related`, add B→A where meaningful.
7. Decay: apply page-level `stale_after` and the schema's fallback decay rule, using its review marker.
   On 3_Personal/ pages a passed `stale_after` means re-confirm the claim against recent logs or mark it
   `status: deprecated` — never delete it, and never reset a claim's confirmation marker during lint.
8. Gaps: note recurring topics with no synthesized page and dangling internal links.

Do NOT append the lint entry to log.md — the runner records it.
Return a one-paragraph summary: contradictions found/resolved, links/orphans fixed, pages flagged, gaps.
"""

# Deterministic post-step run by the runner (not the agent): regenerate the
# always-visible MEMORY.md from the vault's personal facts + recall signal.
MEMORY_PROMOTION_PROMPT = """You are writing MEMORY.md — the few most important, durable facts \
about the user that should ALWAYS be visible to the assistant.

Consolidated personal knowledge:
{personal_facts}

Recently-recalled topics (usage signal — favour these):
{recall_summary}

Write a concise markdown summary, grouped under `##` headers, one fact per bullet. Include only \
durable, high-value facts. Hard limit: {max_lines} lines. Respond with the markdown only.
"""
