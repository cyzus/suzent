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

**During a conversation.** Every few exchanges, or once a chat has been quiet for
about ten minutes, Suzent reads what was said since it last looked and picks out
anything worth keeping, such as a preference, a project detail, or a fact about
you. It adds those to that day's log. It saves facts, not whole conversations.
Reading several exchanges at once means that if you change your mind partway
through, only where you ended up is saved.

A fact about you is only kept when you said it yourself; something the agent
said or guessed is not. Each saved fact carries the words it came from, so you
can see why it was kept. Facts the agent read in a file or on a web page are kept
too, with where they were read. Scheduled tasks are left out of facts about you,
and so is anything that only matters today.

Lessons come from a separate check. When something goes wrong (a command fails,
or you tell the agent it got something wrong) and the same exchanges then show
what fixed it, the agent saves what to do next time and where it applies, such
as a repository or a tool. A failure that was never fixed, or that will not
happen again, like an expired login, teaches nothing and is not saved. This
check also covers scheduled tasks. When a lesson already in your notebook comes
up again, it is counted rather than saved twice; once a lesson about a
repository has come up three times, the dream asks whether to add it to that
repository's agent instructions.

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
  MEMORY.md              # The map of your memory the agent always sees
  archive/
    2026-08-24.md        # One log per day
  persona.md, user.md    # Editable profile notes
```

These files are the real memory. Open them in any text editor. The search
index is rebuilt from them, so a line you delete here is gone.

### MEMORY.md is a map

`MEMORY.md` is loaded into every conversation. It is a short list of links,
one per notebook page, each with a few words on what the page holds:

```markdown
- [[3_Personal/Preferences]] - how you like answers, tools, and formatting
- [[2_Wiki/Experience/Release checks]] - what went wrong in past releases
```

The facts themselves live on those pages, so the map stays small (30 lines by
default). If the file is missing, Suzent drafts one from your page titles;
after that it is yours, and the dream keeps its links current.

`user.md` is for what the agent needs in every conversation, such as your name,
your language and how to address you. Schedules and the state of a project do
not belong there, and other facts about you go on a `3_Personal/` page.

## Managing what's remembered

The **Memory** panel in the app lets you browse, search, and delete what has
been saved.

- **To forget something,** delete it in the panel. It disappears from search
  for good, even after a rebuild. The original daily log keeps the line as
  history.
- **To correct something,** just say the corrected version in a conversation.
  The dream replaces the old fact, and keeps the old value under a
  **History** heading if it was true once.
- **When something is wrong,** say so ("that's not right, I never lived in
  Basel"). Suzent hides it from search straight away and will not save it
  again.
- **When the dream is unsure,** for example two facts disagree, it writes a
  question instead of guessing. The agent may ask you a few of these when they
  come up naturally, and your answer settles them.

## How memory is tidied

Roughly once a day, the dream reads logs it hasn't processed and, for each
fact, does one of four things:

- **Confirm**: the page already says this, so it raises the page's
  `confirmed` count. Facts you repeat often rank higher in search.
- **Sharpen**: the page says something vaguer, so it improves the wording.
- **Supersede**: the page is now wrong, so it corrects it.
- **Add**: the fact is new, so it writes it down.

Each page says what kind it is: facts about you, lessons from past work, or
general knowledge. The dream files each kind where your notebook's `schema.md`
says, or beside existing pages of the same kind, or in the closest folder you
already have. In a new notebook that means `3_Personal/` for facts about you,
`2_Wiki/Experience/` for lessons, and `2_Wiki/` for knowledge. Your folders
don't have to match: the dream never edits `schema.md` and never adds numbered
top-level folders. To steer it, say where each kind goes in `schema.md`.
The dream never touches today's log, and an interrupted run is retried rather than
skipped. Everything it changed is listed in the notebook's `log.md`.

**Facts expire, gently.** Each fact about you gets a review date based on its
kind: never for identity, a year for preferences, six months for technical
setup, three months for goals, three weeks for passing context. After that
date, the dream re-checks it against recent conversations. Expiry never deletes
anything; it only lowers how strongly an unconfirmed fact shows up in search.

When nothing new needs consolidating, the dream audits the notebook instead,
looking for contradictions, broken links, orphaned pages, and stale knowledge.

## Settings

Turn memory on or off in **Settings → Memory System**. Its models are set in
**Settings → Model Roles**: the dream uses the **Dream** role, picking out facts
uses **Memory Extraction**, and memory search uses **Embedding** (see
[Model roles](../../04-models/model-roles.md)).

How often the dream runs, where the notebook lives, and other tuning are in
[Advanced memory settings](./configuration.md).

## Checking and tidying your memory files

Two commands help when memory has grown untidy:

```bash
suzent memory lint
```

```bash
suzent memory cleanup
```

`lint` lists what does not follow the rules above: a `MEMORY.md` that holds
facts instead of links, an overlong `user.md`, oversized pages. `cleanup` writes
suggested fixed versions next to your memory for you to read; it never changes
your files. See [Command line](../../07-reference/cli.md#memory).
