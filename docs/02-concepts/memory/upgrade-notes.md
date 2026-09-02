# Upgrade Notes: what changes for an existing install

Notes for anyone upgrading a running install across the memory-deduplication work.
Nothing here needs action on a fresh install — every item is about state that already
exists on disk before the upgrade.

Ordered by how likely it is to surprise you.

## 1. The first run re-embeds everything, once

`.index_state.json` is now versioned and keyed on `label:filename` instead of the
absolute path. Pre-v2 state is **discarded rather than migrated**, so the first pass
after the upgrade treats every daily log and vault page as new and re-embeds it.

That is deliberate — the old absolute-path keys were why files got skipped forever, so
the discard doubles as the backfill — but it is not free. Budget one embedding call per
chunk across your whole corpus, and expect the first pass to take noticeably longer than
a steady-state one. If you pay per embedding call, this is the line item to expect.

## 2. Check `CONFIG.notebook_dir` before you assume it's empty

If you mount your own vault at `/mnt/notebook` (an Obsidian folder, say), the *default*
vault path under the data dir still gets created, and any run where the mount failed to
resolve will have consolidated into it. That directory can therefore hold real pages
that exist nowhere else — orphaned output from a misrouted run, not a skeleton.

On the machine this work was done on, the default path held 14 consolidated pages —
including a personal profile and a contacts page — written during a single misrouted run
months after the vault had moved. None of them exist in the live vault. They read like a
leftover bootstrap skeleton, and deleting them on that assumption would have been the
only irreversible mistake in this whole body of work.

Suzent no longer reads the wrong vault, but that does not retroactively rescue anything
already stranded in the default path. **Before deleting that directory, diff it against
your real vault.** It will look like a leftover. It may not be one.

## 3. Legacy rows are not redundant copies — export before deleting

If your install predates the markdown tier, your archival index holds rows with no
`source_file`. Nothing can reindex them, no tombstone can retire them, and no
consolidation will fold them in; they sit in retrieval permanently.

The obvious move is to delete them. Measure first. On this install, **2,831 of 2,833 such
rows appear nowhere in any daily log or vault page** — they predate the markdown tier, so
the index is the only copy of that content, and deleting them is data loss.

```bash
python scripts/retire_legacy_rows.py            # report only
python scripts/retire_legacy_rows.py --export   # append them to daily logs
python scripts/retire_legacy_rows.py --apply    # delete, after a backup
```

`--apply` refuses while any row is recorded nowhere else. Re-indexing the exported logs
costs one embedding call per chunk, and the dream will not consolidate dates below its
watermark without a rewind.

## 4. An existing `MEMORY.md` will not be regenerated until it has markers

`MEMORY.md` is now split into a generated zone and a manual zone by HTML comment
markers. A file with no markers cannot be proven to be generator output, so it is treated
as **entirely manual and never overwritten** — the safe default, since the alternative is
destroying notes someone typed.

The practical consequence: if you have an existing `MEMORY.md`, automatic refresh stays
off for it until markers appear. Let a consolidation write the file, or add the markers by
hand, if you want the generated half back.

## 5. Restated facts stop appearing in the daily logs

A fact that restates something already durably recorded, word for word and with no new
specifics, is no longer written to the daily log. It goes to
`notebook/.state/confirmations.jsonl` and reaches the next dream as a confirmation count.

If you audit what memory captured by grepping daily logs, that file is now part of the
picture. A *revision* — anything adding a new number, date, path, quote, or version — is
still written to the log as before, tagged `revision`.

The dreaming panel gained a **pending confirmations** tile for the same reason, and a
dream can now run on that queue alone. So an install that is caught up on logs may still
start a consolidation, and it will not move the watermark when it does.

## 6. Expect vault churn on the first few dreams

Two changes rewrite frontmatter on pages that predate them:

- `3_Personal/` pages with no `stale_after` are queued for revisit and given one from the
  fact-category table.
- Claims that recur pick up `(confirmed Nx, last YYYY-MM-DD)` markers.

If your vault is in git or a sync folder, the first few dreams after upgrading will look
like a large diff touching many personal pages. That is the backfill, not a bug.

## 7. Retrieval order will change

Indexed `importance` used to be a constant `0.5` for every row. It now varies: repeated
confirmations lift a claim, an expiry in the past damps it, `deprecated` sinks it to a
floor, and a claim you verified yourself in `MEMORY.md` takes a floor of `0.9`.

Since `importance` is already a term in hybrid search, results will re-order after the
first reindex. Nothing is removed from retrieval — `deprecated` demotes, it does not
delete, and deletion stays with tombstones so it remains reversible and auditable.

## 8. Stop the app before running the scripts

`scripts/retire_legacy_rows.py` and `scripts/dream_dry_run.py` both assume nothing else
is writing. A concurrent reindex can race a delete. Stop the app, or accept the race.
