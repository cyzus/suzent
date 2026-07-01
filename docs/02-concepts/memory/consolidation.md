# Memory Consolidation

Suzent uses append-only daily logs for fast, lossless capture and a background “dream” runner for slower consolidation into the notebook wiki. The goal is to avoid dropping new or changed facts during normal chat turns while still giving the agent a deduplicated, cross-linked long-term memory over time.

## Source of truth

Memory files, not LanceDB rows, are the durable source of truth:

- `/shared/memory/archive/YYYY-MM-DD.md` stores raw extracted facts from conversations.
- `/mnt/notebook/` (or the configured host notebook path) stores consolidated wiki pages.
- `/shared/memory/MEMORY.md` stores the compact always-visible memory summary.
- `.suzent/memory/` stores the LanceDB search index derived from the files above.

The indexer is the intended writer for archival LanceDB rows. Memory mutations should be represented as file edits and then reindexed, so the vector database can be rebuilt from disk.

## Per-turn capture

After an assistant response, `MemoryManager.process_conversation_turn_for_memories()` extracts facts with the configured extraction model. The write path is intentionally append-only:

1. Convert the turn into extraction text.
2. Ask the LLM for structured `ExtractedFact` objects.
3. Append those facts to today’s markdown daily log.
4. Reindex that day’s archive file into LanceDB.
5. If an extracted fact is high-importance, refresh `MEMORY.md` from important archival rows as a compatibility path until dream promotion supersedes it.

There is no write-time semantic deduplication. Similar or contradictory statements are preserved in the raw log and resolved later by consolidation, where the agent can inspect broader context and existing notebook pages.

Daily log entries use a lean fact-line format:

```md
# Daily Log - 2026-07-01

## 14:05 — abc12345

- [preference] User prefers compact dashboards `ui product`
- [work] User now works at Microsoft `career`
```

## Notebook vault

The notebook is always-on. `WikiManager` creates the vault root if needed, seeds `schema.md`, `index.md`, and `log.md`, and creates the standard zone folders:

- `0_Inbox/`
- `1_Projects/`
- `2_Wiki/Concepts/`, `2_Wiki/Literature/`, `2_Wiki/Syntheses/`, `2_Wiki/Entities/`
- `3_Personal/`
- `4_Assets/`
- `5_Archives/`

After bootstrap, the agent and dream runner maintain the vault through normal file tools and notebook runbooks. User-memory facts are consolidated primarily into `3_Personal/`; domain knowledge belongs under `2_Wiki/`.

## Dream runner

`DreamRunner` is a background `BaseBrain` service that consolidates old daily logs into notebook pages. It never processes today’s in-progress log. Pending dates are archive files whose date is strictly before today and later than the current consolidation watermark.

The runner is gated by configuration:

- `memory_consolidation_enabled`
- `memory_consolidation_interval_seconds`
- `memory_consolidation_min_hours`
- `memory_consolidation_min_facts`
- `memory_consolidation_max_days`
- `memory_consolidation_max_retries`
- `memory_consolidation_timeout_seconds`
- `memory_consolidation_model`

In steady state, the runner waits until enough time and enough facts have accumulated. If the backlog exceeds one configured batch, it “sprints” batch-by-batch until caught up. A batch that repeatedly produces no progress is skipped after the retry limit, which advances the watermark so one bad batch cannot wedge all future consolidation.

## Watermark semantics

The authoritative consolidation watermark is the latest `watermark=YYYY-MM-DD` token in notebook `log.md`.

The dream agent does not own that token. The runner appends the watermark entry only after a productive run. A productive run must satisfy both conditions:

1. The consolidation agent finished cleanly.
2. At least one notebook content page changed.

This prevents a failed or timed-out agent run from partially modifying a page and then causing old raw logs to be treated as fully consolidated. If either condition fails, the watermark stays put and the batch is retried later.

When the watermark advances, archive logs with dates less than or equal to the watermark are considered consolidated. The indexer removes those archive rows from LanceDB so search prefers consolidated notebook pages over obsolete raw log entries. The raw markdown logs remain on disk as immutable history.

## Search indexing

`CoreMemoryFileIndexer` keeps the derived LanceDB index current for:

- Core files: `persona.md`, `user.md`, and `MEMORY.md`.
- Archive logs in `/shared/memory/archive/` that are newer than the watermark.
- Notebook content pages, recursively, excluding root navigation files and `.state/`.

Archive logs are indexed one row per fact line. Core files and notebook pages are indexed by paragraph chunks. The indexer serializes mutations with an async lock, persists file mtimes in `.index_state.json`, and can rebuild the entire user index from files.

Embedding failures are fail-closed: the indexer embeds all rows for a file before deleting stale rows. If embedding generation fails, existing rows remain untouched and the file can be retried on a later pass.

## Tombstones and deletion

User-deleted memories are recorded as normalized text tombstones in notebook `.state/tombstones.jsonl`. During indexing, tombstones are applied to every source type:

- archive fact rows,
- notebook paragraph chunks,
- core-file paragraph chunks.

This keeps deleted content from being resurrected by a full reindex. Exact tombstones cannot catch a later dream pass that rewords the same fact into new text; that kind of semantic cleanup belongs in a later consolidation or lint pass.

## MEMORY.md promotion

After a successful dream consolidation, the runner calls `MemoryManager.promote_memory_md()`. Promotion reads consolidated personal notebook pages under `3_Personal/`, combines them with recent recall signals from `.state/recall_log.jsonl`, and asks the LLM to write a bounded always-visible `MEMORY.md` summary.

During retrieval, `MemoryManager` records best-effort recall snippets. Those snippets are usage signals for future promotion; they do not replace the file-backed source of truth.

## Lint pass

When ingestion is caught up, the same runner can run an editorial lint pass if `memory_lint_enabled` is true and the last lint entry in `log.md` is old enough according to `memory_lint_min_days`. Lint audits the notebook for contradictions, structural problems, orphaned pages, and stale knowledge. Lint entries do not carry watermarks because they do not consolidate new daily logs.
