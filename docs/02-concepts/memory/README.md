# Memory System

Suzent remembers things across conversations — facts you've shared, your preferences, and
context from past sessions. Everything it remembers is stored as plain Markdown files you
can open, edit, or delete yourself.

## What it remembers

After each exchange, Suzent picks out anything worth keeping — a preference, a project
detail, a fact about you — and appends it to that day's log. It doesn't ask, and it
doesn't remember the whole conversation; only the facts.

Overnight, a background pass called the **dream** reads those logs and folds them into
tidy pages: one page per topic, duplicates merged, contradictions resolved. Day-to-day
capture stays fast and lossless; the tidying happens later, when there's time to think
about it.

The result is two kinds of memory:

| | What it holds | Where |
|---|---|---|
| **Conversation memory** | Facts about you, gathered automatically | `/shared/memory/` |
| **Notebook** | Knowledge pages the agent researches and writes | `/mnt/notebook/` |

The notebook is a full Obsidian-compatible vault — see [Notebook](./llm-wiki.md).

## Where your memory lives

```text
/shared/memory/
  MEMORY.md              # The summary the agent always sees
  archive/
    2026-08-24.md        # One log per day, append-only
  persona.md, user.md    # Editable profile blocks
```

Open any of these in a text editor. They are the real memory — the search index is
rebuilt from them, so if you delete a line, it's gone.

### MEMORY.md is half yours

`MEMORY.md` is the short summary loaded into every conversation. It has two halves,
divided by a marker comment:

```markdown
<!-- memory:generated - rewritten on consolidation -->
...Suzent rewrites everything in here...
<!-- /memory:generated - notes below this line are kept -->

Anything you type down here is kept, forever, untouched.
```

Write below the marker to tell Suzent something directly. Notes there outrank anything it
worked out on its own, and no consolidation will overwrite them.

If your `MEMORY.md` has no markers at all — because it predates them — Suzent treats the
whole file as yours and stops regenerating it. See [Upgrade Notes](./upgrade-notes.md).

## Managing what's remembered

From the **Memory** panel in the app you can browse what's been captured, search it, and
delete individual entries. Deleting is permanent for the search index but leaves the
original daily log intact as history.

To forget something, delete it from the panel. To correct something, just say the
corrected version in conversation — a fact that changes an existing one is recorded as an
update, and the dream retires the old version.

## Settings

Memory is on by default. The settings worth knowing:

```yaml
# config/default.yaml
MEMORY_ENABLED: true
```

Everything else is tuning — how often the dream runs, how much it reads at a time, which
model does the extraction. See [Configuration](./configuration.md) for the full list.

## Read more

- [How consolidation works](./consolidation.md) — what the dream does, and when it runs.
- [Notebook](./llm-wiki.md) — the knowledge vault, and how it differs from memory.
- [Upgrade Notes](./upgrade-notes.md) — what changes on an existing install. Read this
  before deleting anything.

Building on the memory system itself? The implementation notes live under
[Development > Memory System](../../03-developing/memory/architecture.md).
