# LLM Wiki

> Pattern originally described by Andrej Karpathy: [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

The LLM Wiki is a structured knowledge base that lives alongside — but is separate from — the conversation memory system. It uses Obsidian-style markdown (wikilinks, callouts, frontmatter) and is organized according to a `schema.md` the agent reads before every operation.

## How it works

- The vault root is `/mnt/notebook` (sandbox) or `${MOUNT_NOTEBOOK}` (host).
- Three agent-maintained navigation files live at the vault root:
  - `schema.md` — vault conventions, folder layout, and page types. The agent reads this first on every operation.
  - `index.md` — catalog of synthesized pages, updated on every ingest or query filing.
  - `log.md` — append-only chronological record of all agent operations.
- The agent reads and writes vault pages directly via `ReadFileTool`/`WriteFileTool`/`EditFileTool`.
- `WikiManager` bootstraps these three files on first init (from `skills/notebook/schema_example.md`), then stays out of the way.

## Distinction from conversation memory

| | Conversation Memory | LLM Wiki |
|---|---|---|
| **Content** | Episodic facts extracted from chats | Synthesized knowledge pages |
| **Structure** | Daily logs + MEMORY.md + LanceDB | Obsidian vault (schema-defined folders) |
| **Written by** | Automatic extraction | Agent directly via file tools |
| **Searched via** | LanceDB hybrid search | GlobTool + GrepTool + wikilinks |
| **Lifetime** | Accumulates across conversations | Persistent; updated by agent on ingest |

## Operational skills

The notebook skill (under `skills/notebook/`) provides the agent with procedures for working with the vault:

- `ingest.md` — procedure for ingesting new content into the vault
- `lint.md` — procedure for auditing and cleaning vault pages
