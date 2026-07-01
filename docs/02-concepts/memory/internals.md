# Memory Internals

This page describes the implementation-level structure of Suzent memory as it exists today.

## Layers

| Layer | Responsibility |
|---|---|
| Agent prompt and tools | `memory_search`, `block_update`, and file access. |
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

.suzent/transcripts/ or configured data paths
  {session_id}.jsonl              # session transcripts
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

`process_conversation_turn_for_memories()` extracts structured facts, appends them to today’s archive log, and asks the shared `CoreMemoryFileIndexer` to reindex the archive file. It returns `MemoryExtractionResult.extracted_facts` for logging and downstream diagnostics.

The current implementation reindexes the whole current-day archive file after a turn rather than appending a single LanceDB row per fact. This preserves the mutation invariant and makes the operation idempotent, at the cost of growing work as the day’s log grows.

### Retrieval path

`retrieve_relevant_memories()` first checks whether the archival index has rows. It then uses either embedding-backed hybrid search or FTS-only search. Results are formatted for prompt injection and logged best-effort to the notebook recall log for later `MEMORY.md` promotion.

### MEMORY.md writers

There are two MEMORY.md update paths:

- `refresh_core_memory_facts()` summarizes high-importance archival rows. This remains as a compatibility path for high-importance per-turn extraction.
- `promote_memory_md()` is the dream-era path. It summarizes consolidated personal notebook pages plus recall signals after successful consolidation.

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

## Transcripts and session state

Conversation transcripts are append-only JSONL files managed by the session layer. Transcript indexing is separate from memory-file indexing and is opt-in via `transcript_indexing_enabled`.

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
