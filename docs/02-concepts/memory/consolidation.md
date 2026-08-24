# How Consolidation Works

Suzent captures fast and tidies up later. Every conversation appends raw facts to a daily
log; a background pass called the **dream** turns those logs into organised notebook
pages. This page explains what that means for you.

## Capture: during the conversation

After each exchange, Suzent extracts anything worth keeping and appends it to today's log:

```md
# Daily Log - 2026-07-01

## 14:05 — abc12345

- [preference] User prefers compact dashboards `ui product`
- [work] User now works at Microsoft `career`
```

Logs are **append-only**. Nothing is edited or removed at capture time, even if it looks
like a repeat or a contradiction of something already known — sorting that out needs more
context than a single exchange provides, so it waits for the dream.

The one exception is a word-for-word repeat of something already recorded. That isn't
written again; it's counted, and the count becomes evidence that the fact matters.

## Consolidation: the dream

Once a day or so, Suzent reads the logs it hasn't processed yet and folds them into
notebook pages. For each fact it finds, it does one of four things:

- **Confirm** — the page already says this. Bump the count: `(confirmed 12x, last 2026-08-20)`.
- **Sharpen** — the page says something vaguer. Replace the wording, keep the count.
- **Supersede** — the page is now wrong. Correct it, and retire the outdated version.
- **Add** — this is new. Write it down.

Consolidated facts about you land in `3_Personal/`; general knowledge goes under `2_Wiki/`.

The dream never touches today's log — that one is still being written to. And it only
marks logs as processed after a run that actually finished and actually changed something,
so an interrupted run is retried rather than skipped.

### Claims expire

Facts about you have a shelf life, and the dream gives each one an expiry based on what
kind of fact it is:

| Kind of fact | Revisited after |
|---|---|
| Identity | never |
| Preference | 1 year |
| Technical setup | 6 months |
| Goal | 3 months |
| Passing context | 3 weeks |

When a claim passes its date, the dream re-checks it against recent conversations: still
true, refresh it; contradicted, correct it; no evidence either way, leave it and let it
carry less weight in search. **Expiry never deletes anything** — it only affects how
strongly a fact surfaces.

### Tidying up

When there's nothing new to consolidate, the dream instead audits the notebook itself —
looking for contradictions between pages, broken links, orphaned pages, and stale
knowledge. New conversations always take priority; the audit only runs once things are
caught up.

## Deleting things

Deleting a memory from the Memory panel records a permanent *tombstone*. The entry
disappears from search and never comes back, even after a full rebuild — but the original
daily log keeps the line, as history you can still read.

This is the only way memory is removed. Everything else — expiry, superseding, marking a
claim deprecated — changes how a fact ranks, not whether it exists.

## Settings

| Setting | Default | What it does |
|---|---|---|
| `memory_consolidation_enabled` | `true` | Turn the dream on or off |
| `memory_consolidation_min_hours` | `24` | Minimum wait between runs |
| `memory_consolidation_min_facts` | `20` | New facts needed before a run is worth it |
| `memory_consolidation_max_days` | `14` | Days of logs read in one run |
| `memory_lint_enabled` | `true` | Run the notebook audit |
| `memory_lint_min_days` | `7` | Minimum wait between audits |

See [Configuration](./configuration.md) for the rest.

Interested in how this is built? See
[Development > Memory System](../../03-developing/memory/architecture.md).
