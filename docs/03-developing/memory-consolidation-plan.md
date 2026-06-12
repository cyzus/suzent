# Memory: Append-Only Writes + Dream-Agent Wiki Consolidation

Design & implementation plan. Closes [#34](https://github.com/cyzus/suzent/issues/34); supersedes PR #36.

Status: **implemented (PR #41) and validated end-to-end.** Branch: `refactor/memory-architecture-append-only`.
Audit fixes C1–C5 / M1–M5 / m1–m5, NEW-1…11, and refinements §A/§B folded in (tagged inline).

**Phase 3 validated end-to-end** with real models (DeepSeek V4-pro agent + Ollama `nomic-embed-text`
embeddings): the dream agent consolidated seeded daily logs into zoned `3_Personal/` pages,
handled the Google→Microsoft state-change with history (`"Currently Microsoft … Previously Google"`),
deduped duplicate facts, the runner wrote the `watermark=` token, regenerated `MEMORY.md`, reindexed,
and retrieval returned the consolidated pages. This surfaced and fixed a **root-cause robustness bug
(C6)**: `EmbeddingGenerator.generate()/generate_batch()` silently returned **zero vectors** on backend
failure, which poisons the vector index (all-zero rows) and breaks retrieval with no signal. Fix:
embedding now **raises** on failure (never fabricates zeros), and `_reindex_file` **embeds all rows
before mutating the index** — so a transient embedding-backend outage leaves the existing index
untouched and the file is retried, instead of deleting rows and storing poison. Covered by
`tests/memory/test_embedding_robustness.py`.
Code anchors re-verified against current `main` (post-pull): `_deduplicate_and_store_facts`,
`refresh_core_memory_facts`, `MarkdownIndexer`, `CoreMemoryFileIndexer`, `_extract_memories`
(call ~1000 / gate ~1406), `MemoryExtractionResult.memories_created` (sole external consumer
`context_compressor.py:638`), `build_agent_config`, `BaseBrain`/`HeartbeatRunner`, `spawn_subagent`,
`process_turn_text(_stream_queue=None)`, `lifecycle.py:219` notebook gate — all present.

---

## 1. Problem

`MemoryManager._deduplicate_and_store_facts` uses a fixed cosine-similarity threshold
(`0.85`) to decide whether a newly extracted fact is a duplicate of an existing memory.
This is a category error: cosine similarity measures *topical proximity*, not *factual
identity*.

- `"I work at Google"` vs `"I work at Microsoft"` → cosine ≈ 0.92 → **dropped as a duplicate**
  (a real update, silently lost — this is #34).
- `"I enjoy hiking"` vs `"I love spending time outdoors"` → cosine ≈ 0.78 → **stored twice**
  (a real duplicate, kept).

No threshold value fixes this — the metric cannot separate "same fact, different phrasing"
from "same topic, different fact." That requires language understanding.

Secondary defect: `_deduplicate_and_store_facts` writes facts **directly** to LanceDB while
`CoreMemoryFileIndexer` independently re-syncs markdown → LanceDB on a 300 s timer. Both
write the same table, racing each other. The markdown store's docstring says *"LanceDB serves
as the search index over this markdown content"* — but the code does the opposite.

## 2. Principles

1. **Cosine retrieves candidates; the LLM decides** (correction / state-change / duplicate / new).
2. **Files are the source of truth; LanceDB is a pure derived index** — see the mutation invariant (§2.1).
3. **The raw daily-log stream is immutable** — history is never destroyed.
4. **No** similarity threshold, importance scalar, or fixed category partition. The only
   numbers are operational (hours, counts, size caps).
5. **Reuse the wiki keeper that already exists** — don't invent a second consolidation engine.

### 2.1 The mutation invariant (absolute)

**No route, manager, or tool ever mutates LanceDB directly. The indexer is the only writer.**
Every memory mutation — create, update, delete — is a **file edit followed by a reindex** of that
file. LanceDB is a disposable projection that can be deleted and rebuilt from files at any time.
After Phase 1, the only callers of `store.add_memory / update_memory / delete_memory` are
`CoreMemoryFileIndexer` (and `TranscriptIndexer`, which is itself file→index). This is a review
checklist item.

## 3. Key insight: the "wiki keeper" already exists

Suzent already has an LLM-driven, markdown-file consolidation system — the **notebook skill**
(`skills/notebook/`). It is *not* autonomous today; it is a set of agent-facing runbooks the
main agent runs on demand:

- **`WikiManager`** (`memory/wiki_manager.py`) — a one-shot bootstrapper. Only if `/mnt/notebook`
  is mounted, it seeds `schema.md` / `index.md` / `log.md`, then is dormant.
- **`ingest.md`** — read `schema.md` → find unprocessed daily logs (newer than the last
  `ingest | daily logs` entry in `log.md` — *the watermark*) → explore vault → write/update
  pages (frontmatter, `[[wikilinks]]`, dedup against existing) → update `index.md` → append to
  `log.md`.
- **`lint.md`** — contradiction escalation (`> [!warning]` on the page + `[!alert]` in `log.md`),
  hierarchy/link/orphan checks, status decay (`active` + `updated` > 90 d → `needs-review`).
- **`schema.md`** — vault zones, page types, frontmatter (`status: active | superseded |
  needs-review`), and **Maintenance Rule #1** (contradiction → `[!warning]` callout + flag in
  `log.md`).

So the watermark, dedup-by-exploration, and full conflict-escalation protocol **already exist
and work when invoked**. This plan does not rewrite them. It:

1. makes the vault **always-on** (not gated on an optional mount),
2. runs the `ingest` procedure on a **gated background schedule** via a **forked agent**,
3. moves the watermark from agent-written to **runner-managed** (deterministic),
4. **indexes the vault into LanceDB** so consolidated pages are retrievable.

The "dream agent" is the **autonomous version of the keeper that already exists.**

## 4. Architecture

```
~/.suzent/
  memory/                              LanceDB vector index (derived)
  sandbox/shared/memory/               operational memory
    persona.md, user.md, MEMORY.md     persona/user = curated always-visible
    archive/YYYY-MM-DD.md              append-only daily logs (IMMUTABLE source of truth)
    sessions/{id}/context.md           ephemeral per-session scratchpad
  notebook/                            THE WIKI VAULT (always-on; DATA_DIR/notebook)
    schema.md, index.md, log.md
    0_Inbox/ 1_Projects/ 2_Wiki/ 3_Personal/ 4_Assets/ 5_Archives/
    .state/  recall_log.jsonl, tombstones.jsonl    (watermark lives in log.md, not here)
```

**Three tiers**

| Tier | Location | Role | Where seen |
|---|---|---|---|
| 1 stream | `archive/YYYY-MM-DD.md` | append-only daily facts (immutable) | on disk; recent ones indexed |
| 2 durable | `notebook/**` wiki pages | deduped, cross-referenced knowledge | search index (on demand) |
| 3 always-on | `MEMORY.md` | few highest-value, most-recalled facts | always in the prompt |

**Data flow.** Every turn appends facts to today's log and indexes it (Phase 1). A gated
background **dream agent** periodically consolidates logs `< today` into wiki pages (Phase 3).
`CoreMemoryFileIndexer` indexes memory files **and** notebook pages into LanceDB; consolidated
logs drop out of the index by watermark (Phase 2). `MEMORY.md` is regenerated from the vault +
recall signal after each dream.

## 5. Locked decisions

1. **Vault** = `~/.suzent/notebook` (always-on), **indexed into LanceDB like memory files**.
   `/mnt/notebook` mount = optional redirect to a user's own Obsidian folder.
2. **Consolidation engine** = autonomous **dream agent** (forked LLM agent, like Claude Code's
   `autoDream`), reusing the `ingest.md` procedure. **Full wiki** from day one.
3. **Dream chat** = one persistent hidden chat `system-dream`, **reset each run**
   (`platform="dream"`, filtered from the UI).
4. **Watermark** = one source of truth in **`log.md`** — the `watermark=YYYY-MM-DD` token on the
   latest `ingest | daily logs` entry (both the dream and manual `ingest` read it). The **runner**
   writes that token, but **only after a verified-productive run** (pages changed), so the entry
   doubles as proof-of-work. No separate state file. Idempotent dream is the safety net.
5. **User facts** → existing **`3_Personal/`** zone; domain knowledge → `2_Wiki/`. `ingest.md`
   gets one clarifying line; no new zone.
6. **`MEMORY.md` promotion** lives in the dream flow (a deterministic post-step), not in
   `ingest.md`.
7. **Phasing**: P1 append-only (#34) → P2 always-on vault + watermark indexing → P3 DreamRunner.

### 5.1 Refinements

- **§A — index granularity.** The diary (daily logs) is indexed **one row per fact** (each `- …`
  line is an atomic statement → precise retrieval, clean per-fact add/delete). The wiki and core
  files are indexed **one row per paragraph chunk** (prose can't be atomized). Replaces the current
  chunk-everything behavior for the diary path.
- **§B — backlog & pacing.** A dream run consolidates **one bounded batch** (`max_days`), judged
  productive by whether a *content* page changed. When **behind** (more than one batch pending, e.g.
  cold-start), the runner **sprints** batch-by-batch ignoring the daily gate; when caught up it
  returns to once a day. A batch that produces nothing `max_retries` times is **skipped** (logged) so
  one bad day can't wedge the backlog — its facts remain in the immutable diary.

---

## 6. Phase 1 — Append-only write path (closes #34)

Goal: stop dropping updates. No write-time dedup; today's log is indexed immediately.

**`memory/manager.py`**
- Delete: `_deduplicate_and_store_facts`, `_add_memory_internal`, `process_message_for_memories`,
  `_extract_facts_simple`; constants `DEDUPLICATION_SEARCH_LIMIT`,
  `DEDUPLICATION_SIMILARITY_THRESHOLD`, `DEFAULT_IMPORTANCE`.
- **Keep `refresh_core_memory_facts` (and `IMPORTANT_MEMORY_THRESHOLD`) for now (C1)** — it is the
  only automatic writer of `MEMORY.md`; deleting it here would freeze the always-visible "facts"
  block until Phase 3. Both are removed in Phase 3 when `promote_memory_md` replaces them.
- `__init__`: `self._core_indexer = CoreMemoryFileIndexer()` (shared with the lifecycle watcher).
- Rewrite `process_conversation_turn_for_memories`: `_extract_facts_llm` →
  `_write_facts_to_markdown` → **delta-index the new entry only** (C4) → return slim result. No
  similarity check. Drop the existing log line referencing `result.memories_created`
  (`manager.py:447`) (M4).
- `_write_facts_to_markdown`: fix `f.category or "general"`; **return the date**.

**`memory/indexer.py`**
- `CoreMemoryFileIndexer`: add `asyncio.Lock`; split `check_and_update` → locked wrapper + `_impl`.
  Add **`append_index_entry(file, fact)`** for the per-turn path — embeds the **one new fact as its
  own row** (diary = one row per fact; §A), keyed by the day's `source_file`, and **updates the
  recorded mtime for that file so the 5-min watcher does not re-embed the whole growing log**
  (NEW-3/C4). Whole-file `reindex_file_now(path,…)` (delete-by-`source_file` + re-embed) is kept for
  rebuilds and is idempotent with the per-turn appends.

**`memory/models.py`**
- `MemoryExtractionResult`: drop `memories_created`/`memories_updated`; keep `extracted_facts`,
  `conflicts_detected`.

**`core/chat_processor.py` (platform guard — prerequisite for P3; also fixes existing subagents)**
- Call site ~1000, gate ~1406. Skip **both memory extraction (B2) and transcript writing/indexing
  (B1)** for system/forked turns — gate on **effective** memory_enabled (per-chat config) or
  `platform in {"subagent","subagent_wakeup","dream"}`, not only global `CONFIG.memory_enabled`.
  (The B1 guard is NEW-7: keeps the dream's own chatter out of memory.)

**`core/context_compressor.py`**
- Drop `created_count` (~481); log `extracted_count` only.

**`memory/lifecycle.py`**
- `_core_file_watch_loop`: use `mgr._core_indexer` (shared), not a fresh instance.

Tests: Google→Microsoft both retrievable (no drop); a subagent/dream turn extracts nothing;
compaction log path works.

---

## 7. Phase 2 — Always-on vault + watermark-aware indexing

Goal: the wiki always exists and is indexed into LanceDB like memory; logs become
watermark-aware in the index; deletes can't resurrect.

**`memory/wiki_manager.py`**
- Default `notebook_path = CONFIG.notebook_dir` (`~/.suzent/notebook`). Bootstrap `schema.md`
  (with `3_Personal/` documented for personal facts), `index.md`, `log.md`, and zone dirs.

**`memory/lifecycle.py`**
- `init_memory_system`: remove the `if notebook_host_path:` gate (~219) — **always** create the
  vault. Use the user-mounted `/mnt/notebook` host path if provided, else `CONFIG.notebook_dir`.
  Store resolved path as `manager.notebook_dir`.

**`memory/markdown_store.py`** (or new `vault_store.py`)
- Vault helpers: recursive page listing, read/write page, read/append `log.md`, read `schema.md`.
- State helpers: `recall_log.jsonl`, `tombstones.jsonl` under `notebook/.state/`. The watermark is
  **not** a state file — it is the `watermark=YYYY-MM-DD` token on the latest `ingest | daily logs`
  entry in `log.md`, read by both the dream and manual ingest.

**`memory/indexer.py::CoreMemoryFileIndexer`**
- **Index source: notebook** — recursive `notebook/**/*.md` (exclude `.state/`); one chunked
  LanceDB entry set per page; `source_type="notebook"`, `source_file=<root-relative path>`
  (avoids collision with memory files); per-page mtime change detection.
- **Granularity (§A)** — diary logs are indexed **one row per fact** (read each `- …` line); notebook
  pages and core files are indexed **one row per paragraph chunk** (`_chunk_by_paragraphs`). Wiki
  prose can't be atomized into facts; diary lines already are atomic facts.
- **Watermark-aware archives** — read the `watermark=` token from `log.md`; index logs `date > W`;
  delete-once logs `date ≤ W`. (Until P3 advances W, all logs are `> W` → identical to today.)
  **Skip tombstoned content** when indexing logs, so user-deleted log facts never resurrect.
- **Constant importance 0.5** everywhere (drop per-source values; ranking = relevance+recency).
- `clear_and_full_reindex(...)`: wipe LanceDB for user, reset mtime state, reindex memory files
  + notebook pages + post-watermark archives.
- **Delete `MarkdownIndexer`** + its regex (now unreferenced).

**`routes/session_routes.py::reindex_memories`**
- Delegate to `manager._core_indexer.clear_and_full_reindex` (clear) / `check_and_update`
  (incremental). Now covers notebook + memory.

**`routes/memory_routes.py::delete_archival_memory`** (file edit → reindex; never mutates LanceDB
directly — §2.1)
- Resolve `memory_id → source_file` from metadata.
- **Notebook page** (editable truth): remove the matching paragraph(s) from the page (content-match
  the stored chunk), rewrite the file, `reindex_file_now(page)`. The fact is gone from the file, so
  a later full reindex cannot resurrect it.
- **Daily log** (immutable): write an **indexer-consulted tombstone** to `tombstones.jsonl` (the
  indexer skips it when indexing logs, so even `clear_and_full_reindex` won't bring it back).
- Complex sub-paragraph removals (one clause out of a synthesis paragraph) are queued as a
  dream/lint correction, not done mechanically.

**`memory/manager.py`**
- `retrieve_relevant_memories` / `search_memories`: append to `recall_log.jsonl` (usage signal).

**`memory_context.py`**
- Reconcile the prompt's memory section to one always-available vault + operational files; drop
  the "notebook not configured, skip" caveat. `MEMORY.md` stays the always-visible block.

**`config/__init__.py`**
- `notebook_dir: str = str(DATA_DIR / "notebook")` + consolidation knobs (§9).

Migration: `POST /memory/reindex {clear_existing:true}` → rebuild from memory + notebook; seed the
watermark by writing an initial `## [<date>] ingest | daily logs  watermark=<before-oldest>` line to
`log.md`.

Tests: vault bootstrapped with schema/index/log + zones; notebook pages retrievable via
`memory_search`; reindex deterministic; archives ≤ W dropped, > W kept; delete writes a tombstone.

---

## 8. Phase 3 — DreamRunner (autonomous consolidation)

Goal: the gated, autonomous dream agent that consolidates logs into the wiki and regenerates
`MEMORY.md`.

### 8.1 How it works (two layers)

**Orchestration — `DreamRunner` (Python, deterministic).** Background loop → gate
(time + volume + lock) → reset `system-dream` chat → fork an LLM agent with file tools → on
success, advance the watermark, reindex, regenerate `MEMORY.md`. The runner owns bookkeeping;
the LLM never touches the watermark.

**Knowledge — the forked agent (autonomous, multi-step).** Runs the `ingest` procedure:
1. **Orient** — read `schema.md`, `index.md`; `Glob` the vault.
2. **Gather** — read daily logs in range (`W < date < today`).
3. **Place** — find the page each fact belongs to via `index.md` + `Glob`/`Grep` +
   `memory_search` ("cosine retrieves candidates, the LLM decides" — no threshold).
4. **Write** — create/update the page, applying the conflict rules (§8.4).
5. **Cross-link** — `## Related` wikilinks.
6. **Record** — update `index.md`; append an ingest entry to `log.md`.

Guardrails: `AgentTool` always denied (no recursion); `PathResolver` confines writes to
`/shared` + `/mnt/notebook`; `memory_enabled=False` + the Phase-1 extraction guard prevent the
dream's own turn from being re-extracted; `wait_for` timeout; the lock prevents overlap; the
agent is told never to edit the read-only daily logs.

### 8.2 Control flow

```
class DreamRunner(BaseBrain):                  # mirrors HeartbeatRunner; started in server.py
  DREAM_CHAT_ID = "system-dream";  _lock = asyncio.Lock()
  interval = CONFIG.memory_consolidation_interval_seconds

  # ephemeral in-memory pacing (NOT the watermark, which lives in log.md)
  _last_attempt_at = 0.0;  _failures = {}            # batch-end-date -> consecutive no-op count

  _tick():
    if not CONFIG.memory_consolidation_enabled or _lock.locked(): return
    W = read_watermark(log.md)                                  # latest `watermark=` token (single source)
    pending = [d for d in archive_dates if W < d < today_utc()] # days not yet consolidated; never today
    if not pending: return
    behind = len(pending) > CONFIG.memory_consolidation_max_days
    if not behind:                                              # steady state: gate on time + volume
      if now - _last_attempt_at < min_hours: return             # backoff on ATTEMPTS (NEW-5)
      if count_fact_lines(pending) < min_facts: return
    # behind (cold-start/backlog): sprint batch-by-batch, ignore the daily gate (B)
    await _run_dream(W, pending)

  _run_dream(W, pending):
    async with _lock:
      _last_attempt_at = now
      batch = pending[: CONFIG.memory_consolidation_max_days];  W_new = batch[-1]   # bounded slice (M2)
      if _failures.get(W_new, 0) >= CONFIG.memory_consolidation_max_retries:        # retry-then-skip (B)
        log.warn(f"skipping un-consolidatable batch ≤{W_new}"); advance_watermark(W_new); return
      pause_core_watcher()                                      # don't index half-written pages (M1/NEW-4)
      reset_chat(DREAM_CHAT_ID)                                 # create-if-missing + clear state/messages
      before = content_pages_state()                            # snapshot for proof-of-work (NEW-6)
      cfg = build_agent_config({"tools": CONFIG.memory_dream_tools, "memory_enabled": False,
              "auto_approve_tools": True, "platform": "dream",
              "sandbox_volumes": [f"{CONFIG.notebook_dir}:/mnt/notebook"],
              "static_instructions": DREAM_SYSTEM_PROMPT})
      try:
        await asyncio.wait_for(ChatProcessor().process_turn_text(
            chat_id=DREAM_CHAT_ID, user_id=CONFIG.user_id,
            message_content=DREAM_INSTRUCTIONS.format(start=W, end=W_new),         # NEW-8 placeholders
            config_override=cfg), timeout=CONFIG.memory_consolidation_timeout_seconds)
      except Exception: log
      finally: resume_core_watcher()
      if content_pages_changed(before):                         # PROOF OF WORK = a content page changed (NEW-6/C2)
        advance_watermark(W_new); _failures.pop(W_new, None)
        await mgr.promote_memory_md(recall_summary, max_lines)  # regenerate MEMORY.md FIRST (NEW-11)
        await mgr._core_indexer.check_and_update(...)           # then index changed pages + new MEMORY.md; drop archives ≤ W_new
      else:
        _failures[W_new] = _failures.get(W_new, 0) + 1          # no-op: don't advance (C2); back off (NEW-5)

  advance_watermark(W_new):                                     # ONLY the runner writes the token (NEW-1/C5)
    append_log_md(f"## [{today}] ingest | daily logs  watermark={W_new}")

  force_run(): bypass time+volume gates (not the lock)          # POST /memory/consolidate
```

### 8.3 The prompts

**`DREAM_SYSTEM_PROMPT`** (role + guardrails):

```
You are Suzent's memory consolidation agent ("dream"). You run autonomously to turn the
raw, append-only daily memory logs into a clean, durable, cross-referenced knowledge vault.

Tools: Read, Write, Edit, Glob, Grep, memory_search.
Filesystem:
- Daily logs (READ-ONLY source): /shared/memory/archive/YYYY-MM-DD.md  — NEVER edit or delete these.
- The vault (your workspace):     /mnt/notebook/  — schema.md, index.md, log.md, zoned pages.

Rules:
- ALWAYS read /mnt/notebook/schema.md first; follow its zones, naming, and frontmatter exactly.
- Improve existing pages; never create near-duplicates. Search before you write.
- Preserve history: when a fact changes over time, record "now X; previously Y" — never silently overwrite.
- Only remove a statement when it is a genuine correction or an exact duplicate.
- Do NOT write to log.md — the runner records the consolidation watermark. Just tidy the pages.
```

**`DREAM_INSTRUCTIONS`** (task message; formatted with the date range):

```
Consolidate the daily memory logs dated after {start} through {end} into the vault.

1. Orient: read schema.md and index.md; Glob /mnt/notebook for existing pages.
2. Read the logs: /shared/memory/archive/*.md dated after {start} through {end}.
3. For each distinct fact/topic:
   a. Find the page it belongs to (index.md + Glob/Grep + memory_search).
      Personal facts about the user → 3_Personal/ ; domain knowledge → 2_Wiki/.
   b. Apply the matching case:
      • Duplicate (same fact reworded)              → do nothing.
      • New, non-conflicting                        → add under the right section.
      • Correction (new entry shows old was wrong)  → replace the wrong statement.
      • Change over time (both true at diff. times) → rewrite as "Currently X (since {date});
                                                       previously Y."  status: active.
      • Genuine conflict you can't confidently resolve → keep the more recent claim, add
        `> [!warning] Conflicting claims: <A> vs <B> (<dates>)`, set frontmatter
        status: needs-review, and prepend `[!alert] Conflict in [[<page>]]` to log.md.
   c. Convert relative dates ("yesterday") to absolute.
4. Add `## Related` wikilinks between related pages.
5. Update index.md. Do NOT write log.md — the runner records the watermark.
Return a one-paragraph summary of what you created, updated, superseded, or flagged.
```

### 8.4 Conflict resolution

The agent compares each new log fact against the relevant existing page and picks one case.
The decisive distinction is **temporal change vs. genuine contradiction**:

| Case | Example | Action |
|---|---|---|
| Duplicate | "likes hiking" / "enjoys hiking" | skip |
| New | first mention of a preference | add |
| **Correction** | "name is Jon" → "it's John" | replace the wrong text (old gone from page; still in raw log) |
| **Change over time** | "works at Google" → "moved to Microsoft" | rewrite: *"Currently Microsoft (since 2026-06-05); previously Google."* History kept; `status: active` |
| **Genuine conflict** (unresolvable) | page "lives in Berlin" vs log "lives in Munich", no "moved" cue | keep the more recent, add `> [!warning] Conflicting claims …`, set `status: needs-review`, prepend `[!alert] Conflict in [[…]]` to `log.md` → **user notified** |

Guarantees: the agent **never silently guesses** on a real contradiction (auto-resolves only on
a clear temporal/correction signal; otherwise escalates), and **nothing is ever lost** (raw logs
are immutable, so any wrong resolution is recoverable by the next dream or a manual `lint`).
This reuses the vault's existing `schema.md` Maintenance Rule #1 and `lint.md` Step-3 escalation.

### 8.5 Which memories it consolidates

Only the append-only daily fact stream: `archive/YYYY-MM-DD.md` with `watermark < date < today`.
**Not** `persona.md`/`user.md` (curated blocks), **not** `MEMORY.md` (regenerated by
`promote_memory_md`), **not** `sessions/*/context.md` (ephemeral), **not** today's log.

### 8.6 Other Phase-3 changes

- **`memory/manager.py`** — add `promote_memory_md(user_id)`: read `3_Personal/` + recall summary →
  `llm_client` → write `MEMORY.md` (≤ `memory_max_lines`). Deterministic single call. **Now** delete
  `refresh_core_memory_facts` + `IMPORTANT_MEMORY_THRESHOLD` (replaced by promotion) (C1).
- **`prompts.py`** — add `DREAM_SYSTEM_PROMPT`, `DREAM_INSTRUCTIONS`.
- **`routes/memory_routes.py`** — `POST /memory/consolidate` → `DreamRunner.force_run()`; register.
- **`server.py`** — instantiate + `start()` `DreamRunner` after `init_memory_system` (~439-462);
  `stop()` in shutdown (~593-624).
- **Volume default (M5)** — inject `/mnt/notebook → CONFIG.notebook_dir` for the dream agent (set in
  `DreamRunner` cfg) **and for the main agent** in **`config.get_effective_volumes()`** (config:255 —
  the function `get_or_create_agent` already calls to resolve volumes) when the user hasn't mapped it,
  otherwise the unified `memory_context` prompt references a `/mnt/notebook` the main agent can't resolve.
- **`skills/notebook/ingest.md`** — (1) personal/user facts → `3_Personal/`; (2) **Step 8 emits the
  same `watermark=YYYY-MM-DD` token** on its `ingest | daily logs` entry, so manual ingest and the
  dream share one watermark format (NEW-2).
- **Clean dream prompt (M3 — resolved)** — `get_or_create_agent` gates memory/context injection on
  `config.memory_enabled` (agent_manager.py:343), so `memory_enabled=False` already yields a focused
  dream prompt with no memory injection. (Extraction still needs the separate platform guard, since
  that path reads global `CONFIG.memory_enabled`.)
- **Watcher pause (M1/NEW-4)** — no pause hook exists today (`_core_file_watch_loop` is a plain loop).
  Add a shared `asyncio.Event` in `lifecycle.py` that `DreamRunner` clears while it holds the lock and
  the watcher awaits; otherwise the watcher can index half-written pages mid-dream.
- **Chat list** — hide `platform="dream"` (confirm subagent also hidden).

Tests: gate respected, `force` overrides; Google→Microsoft → one `3_Personal/` page "now
Microsoft; previously Google"; recursion guard (dream turn → 0 new facts); crash → watermark not
advanced, re-run no dupes; `MEMORY.md` under cap; dream chat is one row, reset each run, hidden.

---

## 9. Config (all operational; none decide fact identity)

```python
memory_consolidation_enabled: bool = True
memory_consolidation_min_hours: float = 24.0
memory_consolidation_min_facts: int = 20
memory_consolidation_interval_seconds: int = 1800
memory_consolidation_timeout_seconds: int = 600
memory_consolidation_max_days: int = 14            # bounded backlog per dream run (M2)
memory_consolidation_max_retries: int = 3          # no-op batches to retry before skip (B)
memory_consolidation_memory_max_lines: int = 200
memory_consolidation_model: Optional[str] = None   # default: cheap/extraction model
memory_dream_tools: list[str] = ["ReadFileTool","WriteFileTool","EditFileTool","GlobTool","GrepTool","MemorySearchTool"]
notebook_dir: str = str(DATA_DIR / "notebook")
```

## 10. Blast radius (by file)

| File | Phase | Change | Risk / downstream |
|---|---|---|---|
| `manager.py` | 1,3 | delete dedup path; append-only turn (delta-index); recall log; `refresh` kept to P3; `promote_memory_md` (P3) | callers `chat_processor:1000`, `context_compressor:631/638` discard/log result |
| `models.py` | 1 | drop `memories_created/updated` | only consumer `context_compressor:481` |
| `chat_processor.py` | 1 | extraction platform guard | fixes existing subagent behavior; touches post-turn path |
| `context_compressor.py` | 1 | drop `created_count` | self-contained |
| `indexer.py` | 1,2 | lock; `append_index_entry` (delta) + `reindex_file_now`; notebook source (recursive); watermark archives + **tombstone-skip**; constant importance; `clear_and_full_reindex`; **delete `MarkdownIndexer`** | `session_routes:241` must switch off `MarkdownIndexer` |
| `lifecycle.py` | 1,2,3 | shared indexer; always-on vault; **watcher-pause `asyncio.Event`** (NEW-4) | startup path |
| `wiki_manager.py` | 2 | default `notebook_dir`; zones | — |
| `markdown_store.py` | 2 | vault + state helpers | additive |
| `memory_context.py` | 2 | unified vault prompt | **every agent system prompt** — keep correct |
| `session_routes.py` | 2 | reindex → `CoreMemoryFileIndexer` | route contract preserved |
| `memory_routes.py` | 2,3 | delete = file-edit→reindex (never LanceDB); `POST /memory/consolidate` | new route registration |
| `config/__init__.py` | 2 | knobs + `notebook_dir` | additive; `config_routes` exposes config |
| `dream_runner.py` | 3 | **new** BaseBrain | depends on ChatProcessor, build_agent_config, PathResolver, DB |
| `prompts.py` | 3 | `DREAM_*` prompts | — |
| `server.py` | 3 | start/stop `DreamRunner` | lifecycle |
| `agent_manager.py` | 3 | default `/mnt/notebook` mount | volume assembly |
| `skills/notebook/*` | 3 | `3_Personal/` routing + **`watermark=` token in Step 8** (NEW-2) | also affects manual `/ingest` |
| chat-list route | 3 | hide `platform="dream"` | UI |

## 11. Edge cases (with handling)

1. **Recursion** (dream turn → extraction → new logs): extraction platform guard (P1). *Required.*
2. **History loss**: state-change kept as "previously X"; raw logs immutable; demotion ≠ deletion;
   full rebuild from logs.
3. **Delete**: file edit → reindex (pages) or indexer-consulted tombstone (immutable logs) — never
   a direct LanceDB delete (§2.1), so nothing resurrects. Caveat: removing one clause from a
   synthesis paragraph isn't mechanical → queued as a dream/lint correction.
4. **Crash mid-dream**: watermark only advances on success; idempotent dream prevents duplicate
   pages on re-run.
5. **In-progress today's log**: window strictly `< today` (UTC); today stays indexed, never
   consolidated.
6. **Concurrent dreams**: `asyncio.Lock` + gate checks it.
7. **Dream vs per-turn write**: disjoint files (today's log vs pages); both reach LanceDB via the
   indexer lock.
8. **Process restart mid-dream**: in-memory lock clears; watermark unadvanced → idempotent re-run.
9. **Dream chat bloat**: persistent + reset-each-run → one row, clean slate; `platform="dream"`
   hidden.
10. **Default mount missing**: dream agent can't reach `notebook_dir` → no-op; assert mount in a test.
11. **Recursive notebook indexing** vs flat archive glob; root-relative `source_file` to avoid
    collisions.
12. **Importance flattened to 0.5**: ranking = relevance+recency; update any importance-order tests.
13. **Transient duplicate** (page + raw log until W advances): accepted; strictly better than dropping.
14. **MEMORY.md overflow**: enforce `memory_max_lines` in promotion.
15. **Tombstone fuzzy match**: reworded facts may slip; documented limitation.
16. **Sandbox vs host**: `/shared` + `/mnt/notebook` resolve in both; dream chat-id-independent.
17. **Multi-user**: single `notebook_dir` under `CONFIG.user_id` — pre-existing single-user limitation.
18. **Empty/cold start**: full-wiki bootstrap creates schema/index/log + minimal pages; dream
    no-ops under the volume gate until enough logs accrue.
19. **Unproductive dream**: the watermark advances only on proof-of-work (pages changed) + a
    runner-written `watermark=` token; a no-op run does not advance (C2).
20. **Watcher vs dream race**: the core-file watcher is paused while a dream holds the lock (M1).
21. **Large backlog**: bounded to `memory_consolidation_max_days` per run; loops across runs (M2).
22. **MEMORY.md continuity**: `refresh_core_memory_facts` is kept through Phases 1–2 and only
    replaced by `promote_memory_md` in Phase 3, so the always-visible block never goes stale (C1).
23. **Per-turn index cost**: the per-turn path delta-indexes only the appended fact, not the whole
    daily log (C4).
24. **Impl checks**: tool class names `ReadFileTool/WriteFileTool/EditFileTool/GlobTool/GrepTool`
    confirmed (m1 ✓); UTC consistency for `today`/watermark (m3); `db.update_chat(agent_state=None,
    messages=[])` resets the dream chat (m4); notebook glob is recursive with root-relative
    `source_file` keys (m5).
25. **Index granularity (§A)**: diary = one row per fact; wiki/core = one row per paragraph chunk.
26. **Cold-start backlog (§B)**: when behind (`pending > max_days`) the dream sprints batch-by-batch,
    ignoring the daily gate; caught up → once a day. A batch that produces nothing `max_retries` times
    is logged and skipped (advance past it) so it can't wedge the backlog — those facts stay in the
    immutable diary.
27. **Watermark single-writer (NEW-1)**: only the runner writes the `watermark=` token; the dream
    prompt must not, and manual `ingest.md` emits the same token format (NEW-2). Manual ingest's token
    is agent-written (less reliable than the dream's runner-written one) — acceptable as it's user-initiated.
28. **No-op backoff (NEW-5)**: an unproductive dream does not advance the watermark (C2) but records
    in-memory `last_attempt_at` and backs off `min_hours`, so it can't re-fork every interval.
29. **Proof-of-work scope (NEW-6)**: "did work" = a *content* page changed, excluding `log.md`/`index.md`.
30. **Dream transcript (NEW-7)**: transcript writing/indexing is skipped for `platform=="dream"` (B1 guard).
31. **Singleton agent vs long dream turn (NEW-10 — resolved)**: `process_turn_text` binds the agent
    into a *local* var at turn start (chat_processor.py:239), and `deps`/volumes/tools likewise (:246),
    so a concurrent user turn recreating the global `agent_instance` cannot swap the dream's in-flight
    agent or escape its file-tool whitelist. Residual: agent-cache churn when dream/user configs
    alternate (perf only; subagents already exercise it).
32. **MEMORY.md index freshness (NEW-11)**: `promote_memory_md` runs *before* `check_and_update` so the
    freshly written `MEMORY.md` is indexed in the same pass (it's always injected regardless, so this is
    cleanliness).

## 12. Migration

One-time `POST /memory/reindex {clear_existing:true}` → `clear_and_full_reindex` wipes LanceDB
and rebuilds from memory + notebook. Seed the watermark by writing an initial
`## [<date>] ingest | daily logs  watermark=<before-oldest-log>` line to `log.md`, so the first
dream folds the full history once (bounded by `max_days` per run). Nothing at risk — raw logs are
the source of truth.

## 13. Rollout

Ship **Phase 1** alone first (small, closes #34, fixes the latent subagent extraction bug). Then
**Phase 2** (always-on vault + indexing, behind the bootstrap + a `clear_and_full_reindex`
migration). Then **Phase 3** (the dream agent) once 1–2 are stable in use.

## 14. Open questions

1. Single vault file growth: notebook scales by pages, so no single-file concern (resolved).
2. **All-or-nothing dream run** vs. per-date watermark — how to stop one persistently-failing day
   blocking progress (retry budget? quarantine?).
3. Default `/mnt/notebook` mount for **main agents** too (preserve "file a query result"), or
   dream-agent-only?
4. Recall-log retention: truncate each run vs. rolling N-day window for a longer promotion signal.
