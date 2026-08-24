"""Re-date indexed rows from their source file instead of from the indexing run.

`add_memory` stamped `created_at` with the moment the row was written, so a reindex
re-dated everything it touched to today. The last vault reindex did exactly that:
1,211 of 1,513 notebook rows now claim to have been created on the day they were
re-embedded, including pages whose files have not been edited since October 2025.

That is not just a cosmetic date. `calculate_final_score` weights results by
`1/(1+age_days)`, so a freshly reindexed corpus takes the maximum recency boost in
every search — a page from last year out-ranks a memory from last week for no reason
but having been re-embedded. The date group headers and the "new" badge are wrong in
the same way, just more visibly.

The indexer now passes a real timestamp (see `CoreMemoryFileIndexer._source_time`),
so rows written from here on are right. This fixes the ones already on disk, without
re-embedding anything: only the `created_at` column changes.

    python scripts/redate_indexed_rows.py            # report only
    python scripts/redate_indexed_rows.py --apply    # rewrite, after a backup

Only rows carrying `source_file` can be fixed — that is the key that points at the
file the date comes from. Legacy direct-insert rows have no such key and are left
alone; `updated_at` is left alone too, because write time is what it means.

Nothing here is safe to run while the app is writing: stop it first.
"""

import argparse
import asyncio
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

# A row whose date is off by less than this is not worth a rewrite — mtimes drift by
# seconds across a OneDrive sync and we would be churning the table for noise.
MIN_DRIFT_DAYS = 1


def _resolve_path(metadata: dict, archive_dir: Path, vault_dir: Path) -> Path | None:
    """The file a row was indexed from, or None if it is not on disk any more."""
    source_file = metadata.get("source_file")
    if not source_file:
        return None
    source_type = metadata.get("source_type") or ""
    root = archive_dir if source_type == "archive_log" else vault_dir
    candidate = root / source_file
    return candidate if candidate.exists() else None


def _source_time(metadata: dict, path: Path | None):
    """Delegate to the indexer, so the repair and the writer cannot disagree."""
    from suzent.memory.indexer import CoreMemoryFileIndexer

    source_file = metadata.get("source_file") or ""
    label = "archive" if (metadata.get("source_type") == "archive_log") else "notebook"
    content = ""
    mtime = birthtime = None
    if path is not None:
        mtime, birthtime = CoreMemoryFileIndexer.file_times(path)
        try:
            # Only the frontmatter is needed, and some vault pages are large.
            content = path.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            content = ""
    return CoreMemoryFileIndexer._source_time(
        label, source_file, content, mtime, birthtime
    )


async def main_async(args: argparse.Namespace) -> int:
    from suzent.config import CONFIG
    from suzent.memory.lancedb_store import LanceDBMemoryStore
    from suzent.memory.lifecycle import resolve_notebook_dir

    uri = args.uri or CONFIG.lancedb_uri
    archive_dir = Path(CONFIG.sandbox_data_path) / "shared" / "memory" / "archive"
    # Not CONFIG.notebook_dir — that path holds a bootstrap skeleton when the user
    # has mounted their own vault, and every lookup against it would miss.
    vault_dir = Path(resolve_notebook_dir())
    print(f"index:   {uri}")
    print(f"archive: {archive_dir}")
    print(f"vault:   {vault_dir}")

    store = LanceDBMemoryStore(uri=uri, embedding_dim=CONFIG.embedding_dimension)
    await store.connect()

    query = store.archival_table.query().select(["id", "metadata", "created_at"])
    rows = (await query.to_arrow()).to_pylist()
    print(f"\n{len(rows)} row(s) in the table")

    buckets = Counter()
    fixes: list[tuple[str, datetime]] = []
    for row in rows:
        try:
            metadata = json.loads(row.get("metadata") or "{}")
        except Exception:
            metadata = {}

        if not metadata.get("source_file"):
            buckets["no source_file (cannot be dated)"] += 1
            continue

        path = _resolve_path(metadata, archive_dir, vault_dir)
        if path is None:
            buckets["source file missing from disk"] += 1
            continue

        wanted = _source_time(metadata, path)
        if wanted is None:
            buckets["no date signal"] += 1
            continue

        current = row.get("created_at")
        if current is not None and current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        if current is not None and abs((current - wanted).days) < MIN_DRIFT_DAYS:
            buckets["already correct"] += 1
            continue

        buckets["to re-date"] += 1
        fixes.append((row["id"], wanted))

    print()
    for kind, n in buckets.most_common():
        print(f"  {n:>6}  {kind}")

    if fixes:
        # Worst first: the point of the report is the size of the lie, not a
        # representative sample of it.
        by_id = {r["id"]: r for r in rows}

        def _drift(item):
            current = by_id[item[0]].get("created_at")
            if current is None:
                return 0
            if current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            return abs((current - item[1]).days)

        print(f"\nlargest corrections (showing {min(args.sample, len(fixes))}):")
        for row_id, wanted in sorted(fixes, key=_drift, reverse=True)[: args.sample]:
            was = str(by_id[row_id].get("created_at"))[:10]
            print(f"  {was}  ->  {wanted:%Y-%m-%d}   ({_drift((row_id, wanted))}d)")

    if not args.apply:
        print("\nDry run. Re-run with --apply to rewrite these dates.")
        return 0

    if not fixes:
        print("\nNothing to do.")
        return 0

    table_dir = Path(uri) / "archival_memories.lance"
    if table_dir.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = table_dir.with_name(f"archival_memories.backup-{stamp}.lance")
        print(f"\nbacking up {table_dir.name} -> {backup.name} ...", flush=True)
        shutil.copytree(table_dir, backup)
    else:
        print(f"\nWARNING: no table directory at {table_dir}; rewriting without backup")

    # Group by target date: rows from one file share a timestamp, so this collapses
    # thousands of single-row updates into one update per distinct date.
    by_date: dict[datetime, list[str]] = {}
    for row_id, wanted in fixes:
        by_date.setdefault(wanted, []).append(row_id)

    done = 0
    for wanted, ids in by_date.items():
        for i in range(0, len(ids), 200):
            chunk = ids[i : i + 200]
            quoted = ", ".join("'" + str(x).replace("'", "''") + "'" for x in chunk)
            await store.archival_table.update(
                where=f"id IN ({quoted})",
                updates={"created_at": wanted.replace(tzinfo=None)},
            )
            done += len(chunk)
        print(f"  re-dated {done}/{len(fixes)}", flush=True)

    if hasattr(store, "optimize"):
        await store.optimize()
    print(f"\nre-dated {done} row(s) across {len(by_date)} distinct date(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--uri", default=None, help="LanceDB path (default: configured)")
    ap.add_argument("--apply", action="store_true", help="actually rewrite the dates")
    ap.add_argument("--sample", type=int, default=8, help="example rows to print")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
