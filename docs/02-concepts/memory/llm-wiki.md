# Notebook

Your agent keeps a second kind of memory: a **notebook**, an Obsidian-compatible
folder of Markdown pages it researches, writes, and tidies itself. Conversation
memory records facts about *you*; the notebook holds knowledge about the *world* —
papers it read, tools it compared, projects it is tracking.

> The pattern comes from Andrej Karpathy's
> [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f), which is
> why you will occasionally see it called that.

## Where it lives

By default the notebook is a folder in your data directory. Point it at an existing
Obsidian vault instead by mounting it — see
[Configuration](./configuration.md#where-the-notebook-lives).

Either way it is ordinary Markdown with `[[wikilinks]]`, so Obsidian, a text editor, or
Git all work on it directly.

## How it's organised

```text
notebook/
  schema.md          # The rules of your vault — edit this to change how pages are filed
  index.md           # Catalog of pages the agent has written
  log.md             # What the agent did, and when
  0_Inbox/           # Raw material you dropped in, waiting to be processed
  1_Projects/        # Active work: roadmaps, meeting notes, TODOs
  2_Wiki/            # The knowledge layer
    Concepts/        #   evergreen ideas
    Literature/      #   one page per paper or article
    Syntheses/       #   comparisons and overviews
    Entities/        #   specific models, datasets, tools, people
  3_Personal/        # Long-term facts about you (written by consolidation)
  4_Assets/          # PDFs and images — never modified
  5_Archives/        # Finished or inactive work
```

**`schema.md` is yours to edit.** The agent reads it before every notebook operation, so
renaming a folder or adding a filing rule there changes what it does next time. It is
seeded once when the vault is created and never overwritten afterwards.

Drop a PDF or a clipping into `0_Inbox/` and the agent will file it on its next pass.

## Notebook vs. conversation memory

| | Conversation memory | Notebook |
|---|---|---|
| **Holds** | Facts about you, extracted from chats | Knowledge pages, written deliberately |
| **Where** | `/shared/memory/` | your notebook folder |
| **Written by** | Automatic extraction after each exchange | The agent, using file tools |
| **Found by** | Semantic search | Links, file search, and semantic search |

The two meet in one place: consolidated facts about you end up as pages under
`3_Personal/`. See [How Consolidation Works](./consolidation.md).

## Tidying

When there is nothing new to consolidate, the agent audits the notebook instead —
contradictions between pages, broken links, orphaned pages, knowledge that has gone
stale. Nothing is deleted; pages are corrected or marked deprecated.

You can also just ask it to research something and write it up; that lands in `2_Wiki/`.

Building on the notebook itself? See
[Development > Memory Internals](../../03-developing/memory/internals.md).
