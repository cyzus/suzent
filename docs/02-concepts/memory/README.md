---
sidebar_position: 1
title: Memory
description: How Suzent remembers you across conversations, where that memory lives, and how to change it.
---

# Memory

**Sovereign continuity.** Memory is where a sovereign AI agent keeps its self.
Suzent's memory is Markdown on your own disk, not rows in a vendor's database,
so you can read it, edit it, track it in Git, and carry it to another machine.
That is why switching models does not reset the agent that knows your work. See
[what makes an agent sovereign](https://suzent.com/sovereign).

Suzent remembers facts you've shared, your preferences, and context from past
conversations. Memory is on by default and needs no setup.

## How it works

**During a conversation.** After each exchange, Suzent picks out anything worth
keeping, such as a preference, a project detail, or a fact about you, and adds
it to that day's log. It saves facts, not whole conversations.

**Overnight.** A background pass called the **dream** reads the new logs and
folds them into tidy pages: one page per topic, duplicates merged,
contradictions resolved. Saving stays fast during the day, and the tidying
happens later.

There are two kinds of memory:

| | What it holds | Where |
|---|---|---|
| **Conversation memory** | Facts about you, gathered automatically | `/shared/memory/` |
| **Notebook** | Knowledge pages the agent researches and writes | `/mnt/notebook/` |

The notebook is an Obsidian-compatible vault. See [Notebook](./llm-wiki.md).

## Where your memory lives

```text
/shared/memory/
  MEMORY.md              # The summary the agent always sees
  archive/
    2026-08-24.md        # One log per day
  persona.md, user.md    # Editable profile notes
```

These files are the real memory. Open them in any text editor. The search
index is rebuilt from them, so a line you delete here is gone.

### MEMORY.md is half yours

`MEMORY.md` is the short summary loaded into every conversation. A marker
comment splits it in two:

```markdown
<!-- memory:generated - rewritten on consolidation -->
...Suzent rewrites everything in here...
<!-- /memory:generated - notes below this line are kept -->

Anything you type down here is kept, forever, untouched.
```

Write below the marker to tell Suzent something directly. Your notes there
outrank anything it worked out on its own, and the dream never overwrites them.

If your `MEMORY.md` has no markers (because it predates them), Suzent treats
the whole file as yours and stops regenerating it.

## Managing what's remembered

The **Memory** panel in the app lets you browse, search, and delete what has
been saved.

- **To forget something,** delete it in the panel. It disappears from search
  for good, even after a rebuild. The original daily log keeps the line as
  history.
- **To correct something,** just say the corrected version in a conversation.
  The dream replaces the old fact.

## How memory is tidied

Roughly once a day, the dream reads logs it hasn't processed and, for each
fact, does one of four things:

- **Confirm**: the page already says this, so it bumps a counter such as
  `(confirmed 12x, last 2026-08-20)`.
- **Sharpen**: the page says something vaguer, so it improves the wording.
- **Supersede**: the page is now wrong, so it corrects it.
- **Add**: the fact is new, so it writes it down.

Facts about you go into the notebook's `3_Personal/` folder; general knowledge
goes under `2_Wiki/`. The dream never touches today's log, and an interrupted
run is retried rather than skipped.

**Facts expire, gently.** Each fact about you gets a review date based on its
kind: never for identity, a year for preferences, six months for technical
setup, three months for goals, three weeks for passing context. After that
date, the dream re-checks it against recent conversations. Expiry never deletes
anything; it only lowers how strongly an unconfirmed fact shows up in search.

When nothing new needs consolidating, the dream audits the notebook instead,
looking for contradictions, broken links, orphaned pages, and stale knowledge.

## Settings

Turn memory on or off, and pick the models it uses, in
**Settings → Memory System**. The dream uses the **Dream** model role, and
memory search uses the **Embedding** role (see
[Model roles](../providers.md#model-roles)).

How often the dream runs, where the notebook lives, and other tuning are in
[Advanced memory settings](./configuration.md).
