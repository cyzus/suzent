---
sidebar_position: 8
---

# Memory Internals

This page describes the implementation-level structure of Suzent memory as it exists today.

## Layers

| Layer | Responsibility |
|---|---|
| Agent prompt and tools | `memory_search`, `memory_update`, and file access. |
| `MemoryManager` | Extraction, retrieval, and core memory formatting. |
| `MarkdownMemoryStore` | File-backed operational memory plus notebook state helpers. |
| `CoreMemoryFileIndexer` | Converts memory files into embedding rows in LanceDB. |
| `LanceDBMemoryStore` | Derived hybrid and semantic search index. |
| `WikiManager` + notebook skill | Vault bootstrap, schema, ingest, lint, and wiki-file conventions. |
| `DreamRunner` | Autonomous daily-log consolidation and notebook lint scheduling. |

## On-disk layout

```text
DATA_DIR/
  memory/                         # LanceDB derived index
  notebook/                       # default always-on wiki vault
    schema.md
    index.md
    log.md                        # consolidation watermark + operation log
    .state/
      recall_log.jsonl
      tombstones.jsonl
      rejected.jsonl              # claims the user said are wrong
      confirmations.jsonl         # restatements waiting for the dream
      superseded.txt              # log lines the dream folded, for the runner to retire
      review_queue.md             # open questions the dream could not settle
      dream_ops.md                # the dream's op log, flushed to log.md by the runner
      capture_dropped.jsonl       # candidates the capture gates dropped, with codes
      cleanup/YYYY-MM-DD/         # `suzent memory cleanup` drafts
    0_Inbox/
    1_Projects/
    2_Wiki/
    3_Personal/
    4_Assets/
    5_Archives/
  sandbox/shared/memory/          # agent-visible operational memory
    persona.md
    user.md
    MEMORY.md
    .index_state.json
    archive/
      YYYY-MM-DD.md
```

In sandbox mode, the agent sees operational memory as `/shared/memory/` and the notebook as `/mnt/notebook/`. In host mode, configured mount paths can be shown in the prompt instead.

## MarkdownMemoryStore

`MarkdownMemoryStore` manages file-backed memory:

- `archive/YYYY-MM-DD.md` daily logs.
- `MEMORY.md` curated long-term summary.
- `persona.md` and `user.md` core blocks.
- Project-scoped `context.md` files.
- Notebook `log.md` helpers for watermark and lint entries.
- Notebook `.state/recall_log.jsonl` retrieval usage signals.
- Notebook `.state/tombstones.jsonl` normalized deletion tombstones.

Reads tolerate invalid UTF-8 bytes with replacement so a single bad paste does not wedge consolidation or indexing.

## MemoryManager

`MemoryManager` coordinates extraction, retrieval, and core memory formatting.

### Core blocks

Core memory is file-backed when markdown memory is enabled:

| Block | File |
|---|---|
| `persona` | `/shared/memory/persona.md` |
| `user` | `/shared/memory/user.md` |
| `facts` | `/shared/memory/MEMORY.md` |
| `context` | project `context.md` when a chat/project is available |

Missing blocks fall back to built-in defaults.

### Extraction path

`process_conversation_for_memories()` takes a batch of turns from `ExtractionQueue` (see memory-architecture.md), extracts structured facts, appends them to today’s archive log, and asks the shared `CoreMemoryFileIndexer` to reindex the archive file. It returns `MemoryExtractionResult.extracted_facts` for logging and downstream diagnostics.

The current implementation reindexes the whole current-day archive file after a batch rather than appending a single LanceDB row per fact. This preserves the mutation invariant and makes the operation idempotent, at the cost of growing work as the day’s log grows.

### Retrieval path

`retrieve_relevant_memories()` first checks whether the archival index has rows. It then uses either embedding-backed hybrid search or FTS-only search. Results are formatted for prompt injection and logged best-effort to the notebook recall log for later `MEMORY.md` promotion.

### MEMORY.md

No code path regenerates MEMORY.md. `ensure_memory_map()` drafts a pointer map from notebook page titles only when the file is missing or empty; after that the dream and the user maintain it. `lint_memory_files()` returns the contract findings described in memory-architecture.md.

## CoreMemoryFileIndexer

The indexer watches and reindexes:

- `persona.md`, `user.md`, `MEMORY.md`,
- `archive/YYYY-MM-DD.md`,
- notebook content pages under the vault root.

It excludes root notebook navigation files (`schema.md`, `index.md`, `log.md`) and files under `.state/`.

Index granularity differs by source:

| Source | Row granularity | Metadata source type |
|---|---|---|
| Archive logs | one row per `- [category] ...` fact line | `archive_log` |
| Notebook pages | paragraph chunks | `notebook` |
| Core files | paragraph chunks | `core_file` |

The indexer persists mtimes in `/shared/memory/.index_state.json`. If a file has the same mtime as the saved state, it is skipped. `clear_and_full_reindex()` deletes user rows and rebuilds from core files, notebook pages, and post-watermark archive logs.

The indexer embeds all new rows before deleting stale rows for a file. This keeps transient embedding failures from erasing working search rows or writing unusable placeholder vectors.

## LanceDBMemoryStore

`LanceDBMemoryStore` owns LanceDB tables and search operations. It still supports legacy core block storage as a fallback when markdown storage is unavailable, but the normal path uses markdown files for core blocks and treats LanceDB as a disposable search projection.

The archival table stores indexed content with metadata such as source type, source file, category, tags, chunk index, user id, chat id, importance, and timestamps. Search combines vector retrieval and full-text search where available.

## WikiManager

`WikiManager` is an idempotent bootstrapper for the notebook vault. It creates the root, seeds `schema.md` from `skills/notebook/schema_example.md`, creates a starter `index.md` and `log.md`, and ensures the standard zone folders exist. It does not continuously manage wiki content after bootstrap.

## DreamRunner

`DreamRunner` is the autonomous consolidation service. It runs in the background when memory consolidation is enabled and a memory manager with markdown and LLM support exists.

Main responsibilities:

- Determine pending archive dates from the watermark in notebook `log.md`.
- Skip today’s in-progress daily log.
- Batch pending dates by `memory_consolidation_max_days`.
- Start a hidden dream chat for the consolidation agent.
- Run the notebook ingest instructions over daily logs.
- Advance the watermark only after a clean agent run with content-page changes.
- Regenerate `MEMORY.md` from consolidated personal knowledge.
- Schedule reindexing after durable consolidation.
- Run notebook lint when ingestion is caught up and lint is due.

The dream runner exposes frontend-safe status fields including pending dates, pending fact count, progress percentage, last results, lint state, and gate settings.

## Notebook skill

The notebook skill supplies operational runbooks:

- `SKILL.md` explains the vault contract and requires reading `schema.md` first.
- `ingest.md` describes how to compile raw sources and daily logs into notebook pages.
- `lint.md` describes editorial checks for contradictions, structure, and stale pages.
- `schema_example.md` defines zones, page types, frontmatter, links, and maintenance rules.

The dream prompt adapts the ingest workflow by making the runner own the watermark entry.

## Session state

The chat event log is the only record of a conversation; memory extraction reads it directly (see [Memory architecture](./memory-architecture.md#write-path-in-batches-of-turns)). Earlier versions also wrote a JSONL transcript copy per chat under `transcripts/`; nothing writes or indexes it now, and an old folder can be deleted.

State snapshots are inspectable JSON mirrors of agent state. They support UI/debug workflows but are not the memory source of truth.

## Deletion model

Deleting an archival memory removes the indexed row and records a normalized tombstone. Reindexing checks tombstones before adding archive facts, notebook chunks, or core chunks. This makes deletion durable across a full rebuild as long as the future text exactly normalizes to the tombstoned content.

## Failure behavior

The memory system is designed to avoid silent loss:

- Per-turn extraction stores raw facts without semantic deduplication.
- Dream watermarks do not advance on failed or non-productive runs.
- Embedding failures abort file replacement before old rows are deleted.
- Tombstones are applied during every source-type reindex.
- Invalid bytes in markdown are replaced during reads instead of aborting the whole pass.

## HTTP API

The memory routes are registered in `src/suzent/server.py` and documented for users in
[HTTP API: Memory](../protocols/http-api.md#memory).
An adjacent session route belongs to the session layer rather than memory:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/session/{id}/state` | GET | Get agent state snapshot |

## Tombstones do not change a file's mtime

The indexer is delete-then-add keyed on mtime, so appending a tombstone does not cause the
affected file to be reindexed. Every tombstone write must be paired with an explicit
reindex of the dates it touches.
