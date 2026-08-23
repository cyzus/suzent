# Memory Deduplication

Companion to [Memory Consolidation](./consolidation.md). That page describes how the
append-only write path and the dream runner are *meant* to work. This page records
what the live data actually looks like, why duplicates accumulate, and the plan for
fixing it.

## The measurement

Near-duplicate rate in the archival index, cosine over the stored embeddings. A row
counts as redundant when an earlier row exceeds the threshold.

| write path | rows | ≥0.995 | ≥0.95 | ≥0.92 |
| --- | ---: | ---: | ---: | ---: |
| `legacy_direct` (pre-June, had write-time dedup) | 2833 | 0.0% | 0.0% | 0.0% |
| `archive_log` (current path) | 615 | 0.3% | 10.1% | 25.4% |
| `notebook` (dream output) | 1342 | 14.7% | 15.6% | 17.6% |

On disk the backlog is larger than the index suggests: 13,102 fact lines across 129
daily logs, 340 exact repeats, and 581 token-set near-duplicates in 279 clusters. The
largest cluster is a single identity fact written 64 times across 26 distinct days.

Most duplication is a paraphrase where one side is strictly less informative:

```text
0.982  A: [preference] The user wants to be reminded to drink water hourly from 9 AM to 9 PM daily.
       B: [preference] User wants to be reminded to drink water daily.
```

Exact-match deduplication keeps both. Similarity deduplication alone would keep the
wrong one half the time.

## Why duplicates accumulate

### Extraction is context-free (fixed)

`FACT_EXTRACTION_SYSTEM_PROMPT` and `format_fact_extraction_user_prompt` passed only the
current conversation turn. The extraction model never saw existing memory and was never
told to skip what is already known, so stable identity and preference facts were
re-extracted every time they were mentioned.

The write path now retrieves the nearest `KNOWN_FACTS_LIMIT` facts and renders them into
the prompt under an "already in memory" heading, with a rule that permits — and
explicitly prefers — emitting a fact that *changes* one of them. Recall is best-effort:
a search failure returns nothing and extraction proceeds exactly as before, because
enriching the prompt must never be able to block a memory write.

### Nothing deduplicates the archival index (fixed)

Write-time deduplication was removed in `98a39a3b` (fixes #34) because a 0.85 cosine
threshold silently dropped *updates* to facts. The intended replacement was the dream
consolidation pass — but the dream consolidates into the notebook vault, while
`DREAM_SYSTEM_PROMPT` declares the daily logs read-only and `DREAM_INSTRUCTIONS` step 3b
resolved a duplicate by doing nothing. The lint pass audits the vault only.

The archival index is derived from the logs, so a duplicate written today was permanent.

Step 3b now ends in a retirement: after folding a log line into a page, the dream appends
the fact text to `notebook/.state/superseded.txt`. That file is the hand-off. The runner —
not the agent — reads it in `_retire_superseded`, tombstones each line, reindexes every
day whose log contains it, and only then truncates it. Ordering is deliberate: a crash
before the truncate replays the same lines, which is idempotent, while clearing first
would lose them.

The split keeps each side to what it is good at. The agent writes files, which is its only
declared capability; index mutation stays with the runner. And the logs are still never
rewritten, so the race with the live write path appending to today's log cannot happen.

Two guards worth knowing about:

- Lines shorter than `MIN_SUPERSEDED_CHARS` (24) are refused. Date lookup is a normalized
  substring match, so a fragment like "dark mode" would match logs it never came from.
- The match is deliberately loose in the other direction. A false positive costs one
  redundant reindex, which is delete-then-add and therefore harmless; a *missed* date
  would strand the row in the index with no mtime change to ever bring the watcher back.

### The dream barely runs (fixed)

`DreamRunner._failures` was ephemeral pacing state, held only in memory. It is the
counter behind retry-then-skip, which exists so that a batch which keeps producing
nothing cannot wedge the backlog.

Because the counter reset on every process start, retry-then-skip only fired if the app
stayed up long enough for `memory_consolidation_max_retries` consecutive attempts on the
same batch. On a desktop app that restarts regularly, a batch that failed once kept
failing from a fresh counter forever, and the watermark never advanced — locally it sat
at `2026-03-11` for five months.

The counters now live in the vault's `.state/dream_state.json`, hydrated once per
process and written back on every mutation.

## The indexer is not append-only

Worth stating explicitly, because it is easy to assume otherwise: only the markdown
history is append-only.

`CoreMemoryFileIndexer._reindex_file` is delete-then-add, per file — `delete_memories_by_source_date`
for archive logs, `delete_memories_by_source_file` for notebook and core files — and its
trigger is mtime. Rewriting a daily log would converge the index with no new machinery.

Log rewriting is still the wrong tool, for three reasons:

1. Duplication is cross-day, so a useful pass must edit many files, not one.
2. Today's log is appended to by the live write path; read-modify-write races with it.
3. Logs at or below the watermark are dropped from the index anyway.

### Tombstones are the right tool

`read_tombstones()` filters by normalized content at index time for archive facts and
notebook chunks alike, and the delete route already implements the full flow:

```text
append_tombstone(content) → reindex_file_now(that day's log) → row is gone
```

History stays intact; the derived row disappears. The trap — and the reason that route
calls reindex explicitly — is that appending a tombstone does not change the log's
mtime, so the watcher never notices on its own. **Every tombstone write must be paired
with an explicit reindex of the affected dates.**

## Target workflow

### Tiers get one job each

Today the log and the vault compete: both are indexed at equal weight, so repeated raw
extractions drown out consolidated pages.

| tier | file | job | writer |
| --- | --- | --- | --- |
| Capture buffer | `archive/YYYY-MM-DD.md` | Lossless, fast, never reasoned over at write time | write path (append only) |
| Knowledge base | `notebook/**/*.md` | Deduplicated claims with provenance and lifecycle | dream only |
| Index | LanceDB | Derived; rebuilt per file | indexer only |

### Write path

Two new steps around the existing extraction call:

1. Retrieve roughly ten nearest known claims and inject them into the extraction prompt
   under an "already known — emit a fact only if it is new, or changes one of these"
   heading. This removes the repetition at its source without reintroducing #34: the
   model can still emit a revision, it just has to know it is writing one.
2. Classify each extracted fact against that retrieved set:

   | similarity | outcome | written |
   | --- | --- | --- |
   | ≥ 0.97, no new specifics | confirmation | one line to `confirmations.jsonl` |
   | 0.90 – 0.97 | revision | new fact line, tagged as revising |
   | < 0.90 | new | new fact line |

   The confirmation sidecar exists for the same reason tombstones do: the write path
   must never edit the vault, and appending to JSONL is race-free.

### Dream

The dream gains two queues beyond its current one:

- **Ingest** — logs in `(watermark, yesterday]`. Never today's log.
- **Confirm** — fold `confirmations.jsonl` into claim counters, then truncate it.
- **Revisit** — vault claims past their `stale_after`.

The duplicate rule in ingest is no longer "do nothing". All four outcomes are live:
confirm (bump the count), sharpen in place (replace the wording, keep the count), supersede,
or add as novel.

Confirmation is recorded on the bullet, not in frontmatter:

```markdown
- Wants to be reminded to drink water hourly from 9 AM to 9 PM. (confirmed 12x, last 2026-08-20)
```

This is OKF's `sources[].usage_count` in the only place it can go: OKF frontmatter is
per-document, and these claims are bullets sharing a page rather than a document each. The
marker's absence means confirmed once, so no page needs migrating. A repeat that
*contradicts* the bullet is explicitly not a confirmation — it resets the count and takes
the correction path, or a reversal would count as evidence for the thing it reverses.

`stale_after` on `3_Personal/` pages is derived from the fact category rather than guessed:
identity never, `preference` a year, `technical` six months, `goal` three months, `context`
three weeks. Lint honours it by re-confirming or deprecating, never deleting.

These rules are stated in `DREAM_INSTRUCTIONS` as well as in `schema_example.md`, because
`schema.md` is copied into a vault once at bootstrap and is user-editable afterwards — every
existing vault predates them. `verified:` is defined in the profile but nothing writes it
yet; wiring a user's core-memory edit to a `human:` actor is still open.

The reconcile phase runs **in the runner, not the agent** — `_retire_superseded` reads the
hand-off file, tombstones, and calls `reindex_file_now` per affected date.

### Borrowed from the Open Knowledge Format

[OKF v0.2](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md)
frontmatter is per-document, so it maps onto notebook vault pages — which today carry no
frontmatter at all — and not onto individual log fact lines. Daily logs stay dumb.

Adopted field names, used as the spec defines them (producer-defined keys are explicitly
permitted, so partial adoption is within its rules):

- `status: draft | stable | deprecated` — `deprecated` is a softer tombstone: the claim
  stays readable and linkable but leaves retrieval ranking, and it is reversible.
- `stale_after` — an absolute instant that gives the dream a revisit queue. Defaults are
  derived from the existing fact `category` rather than guessed per fact by the
  extractor: identity effectively never, `preference` a year, `technical` six months,
  `goal` three months, `context` three weeks.
- `verified: [{by, at}]` — with OKF's actor convention, so a user editing a core memory
  block is a `human:` verification that outranks anything the extractor produced. This
  also supplies the contradiction-resolution rule the system currently lacks.
- `generated: {by, at}` — uniform provenance across logs, vault, and core files.
- `sources[].usage_count` — the most useful borrowing for this problem. A fact extracted
  64 times is not 64 facts; it is one claim confirmed 64 times. Collapsing repeats into
  a counter turns the worst noise source into a ranking signal.

Not adopted: the Attested Computation family (`runtime`, `parameters`, `computation`,
`executor`, `attester`), `resource` URIs (the vault already uses `[[wikilinks]]`), and
formal `okf_version` conformance.

## Sequence

1. ~~Make the dream actually run — persist the retry counter so retry-then-skip
   survives restarts.~~ Done. Everything below assumes consolidation happens.
2. Repair the index: ~~key the indexer state on `label:filename` rather than absolute
   paths so it stops leaking between machines~~ (done — discarding the old path-keyed
   state costs one full reindex, which doubles as the backfill for the window above the
   watermark), and retire the legacy pre-June rows.
3. ~~Add the already-known context to extraction.~~ Done.
4. ~~Stop the dream from resolving duplicates by doing nothing — retire folded-in log
   lines via the tombstone hand-off.~~ Done.
5. ~~Add OKF frontmatter to vault pages (writer side): the personal-page contract, the
   confirmation marker, and category-derived `stale_after`.~~ Done. Ranking on those
   signals is not wired yet.
6. Run a catch-up dream over the backlog with ingest and confirm enabled.
7. Add the write-path classifier and the revisit queue, once there is a populated claim
   set for them to work against.

Steps 3 and 5 are independent. Step 7 should not land before step 6 — the classifier is
only as good as the claims it compares against.
