"""Report on — and optionally delete — archival rows that can never be reindexed.

The archival table is a *derived* index: every current row is produced by reindexing a
markdown file, and `_reindex_file` is delete-then-add keyed on that file. Rows written
by the pre-June direct-insert path carry no `source_file`, so no file will ever replace
them, no tombstone can retire them, and no consolidation will ever fold them in. They
sit in retrieval permanently, at the same importance as everything else.

What the dry run found, and why the order below matters: these rows are not redundant
copies of anything. A 120-row sample checked against every daily log and every vault
page found **zero** of them recorded in markdown — not reworded, not summarised, not at
all. They predate the markdown tier, so the index is the only place that content exists.
Deleting them is data loss, not index cleanup.

So the safe sequence is export first, delete second:

    python scripts/retire_legacy_rows.py                 # report only
    python scripts/retire_legacy_rows.py --export        # write them to daily logs
    python scripts/retire_legacy_rows.py --apply         # delete, after a backup

`--export` appends each row to the daily log for the date it was created, which puts it
in the append-only tier where everything else lives; the indexer then owns it through a
`source_file` like every other row, and the dream can consolidate it. Only after that is
`--apply` merely deleting a duplicate. `--apply` copies the table directory next to
itself first, so it is reversible by restoring that copy.

Note that re-indexing exported logs costs one embedding call per chunk, and that the
dream will not consolidate dates below its watermark without a rewind.

Nothing here is safe to run while the app is writing: stop it, or accept that a
concurrent reindex may race the delete.
"""

import argparse
import asyncio
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


def _classify(metadata: dict) -> str:
    """Which write path produced this row.

    `source_file` is the reindexable key. Its absence is the whole problem: such a row
    is unreachable from every mechanism that maintains the index.
    """
    source_type = metadata.get("source_type") or ""
    if metadata.get("source_file"):
        return source_type or "indexed (no source_type)"
    if source_type:
        return f"orphaned: {source_type}"
    return "legacy_direct"


async def load_rows(table) -> list:
    """Every archival row as a dict, minus the vector column.

    The vector is thousands of floats per row; reading it just to count metadata would
    pull the whole index off disk for nothing.
    """
    query = table.query().select(
        ["id", "content", "metadata", "importance", "created_at"]
    )
    return (await query.to_arrow()).to_pylist()


def _markdown_corpus(archive_dir: Path, vault_dir: Path) -> str:
    """Every daily log and vault page, normalised, as one searchable blob."""
    parts = []
    for root in (archive_dir, vault_dir):
        if not root or not root.exists():
            continue
        for path in root.rglob("*.md"):
            if ".state" in path.parts:
                continue
            try:
                parts.append(
                    " ".join(path.read_text(encoding="utf-8", errors="replace").split())
                )
            except OSError:
                continue
    return " ".join(parts).lower()


def count_unrecorded(rows: list) -> int:
    """How many rows' text cannot be found in the markdown tier.

    Matched on a 90-character prefix: long enough that a hit is not a coincidence,
    short enough to survive a trailing edit. Substring rather than similarity, because
    the question is "is this literally written down somewhere", not "is it implied".
    """
    from suzent.config import CONFIG
    from suzent.memory.lifecycle import resolve_notebook_dir

    # Not CONFIG.notebook_dir: when the user mounts their own vault at /mnt/notebook,
    # that default path holds a stale bootstrap skeleton, and checking against it would
    # report every row as unrecorded no matter what the real vault contains.
    corpus = _markdown_corpus(
        Path(CONFIG.sandbox_data_path) / "shared" / "memory" / "archive",
        Path(resolve_notebook_dir()),
    )
    if not corpus:
        return len(rows)
    missing = 0
    for row in rows:
        text = " ".join(str(row.get("content", "")).split()).lower()[:90]
        if text and text not in corpus:
            missing += 1
    return missing


def export_to_daily_logs(rows: list, archive_dir: Path) -> int:
    """Append each legacy row to the daily log for the date it was created.

    The daily logs are append-only, so this only ever adds a section; the indexer picks
    the file up on its next pass and the row finally acquires a `source_file`. Rows with
    no usable date go to a single `legacy-undated.md` rather than being guessed at.
    """
    archive_dir.mkdir(parents=True, exist_ok=True)
    by_date: dict = {}
    for row in rows:
        date = str(row.get("created_at") or "")[:10]
        if len(date) != 10:
            date = "legacy-undated"
        by_date.setdefault(date, []).append(row)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    written = 0
    for date, group in sorted(by_date.items()):
        path = archive_dir / f"{date}.md"
        lines = [
            f"\n## legacy import — {stamp}\n",
            "<!-- Rows recovered from the pre-June direct-insert index, which had no "
            "markdown record. Content verbatim; category unknown. -->\n",
        ]
        for row in group:
            content = " ".join(str(row.get("content", "")).split())
            if content:
                lines.append(f"- [legacy] {content}")
                written += 1
        if not path.exists():
            path.write_text(f"# Daily Log - {date}\n", encoding="utf-8")
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return written


async def main_async(args: argparse.Namespace) -> int:
    from suzent.config import CONFIG
    from suzent.memory.lancedb_store import LanceDBMemoryStore

    uri = args.uri or CONFIG.lancedb_uri
    print(f"index: {uri}")
    store = LanceDBMemoryStore(uri=uri, embedding_dim=CONFIG.embedding_dimension)
    await store.connect()

    rows = await load_rows(store.archival_table)
    buckets = Counter()
    legacy = []
    for row in rows:
        try:
            metadata = json.loads(row.get("metadata") or "{}")
        except Exception:
            metadata = {}
        kind = _classify(metadata)
        buckets[kind] += 1
        if kind == "legacy_direct":
            legacy.append(row)

    print(f"\n{len(rows)} archival rows")
    for kind, n in buckets.most_common():
        print(f"  {n:>6}  {kind}")

    if not legacy:
        print("\nNothing to retire.")
        return 0

    dates = sorted(str(r.get("created_at"))[:10] for r in legacy if r.get("created_at"))
    if dates:
        print(f"\nlegacy rows span {dates[0]} -> {dates[-1]}")

    for row in legacy[: args.sample]:
        print(f"  - {' '.join(str(row.get('content', '')).split())[:110]}")

    unrecorded = count_unrecorded(legacy)
    print(
        f"\n{unrecorded} of {len(legacy)} legacy row(s) appear nowhere in markdown "
        f"— for those, this index is the only copy."
    )

    if args.export:
        written = export_to_daily_logs(legacy, args.export)
        print(f"exported {written} row(s) into daily logs under {args.export}")
        print("Reindex (or let the watcher catch up), then re-run with --apply.")
        return 0

    if not args.apply:
        print(
            f"\n{len(legacy)} row(s) would be deleted. Export them first "
            f"(--export), then re-run with --apply."
        )
        return 0

    if unrecorded and not args.force:
        print(
            f"\nRefusing to delete: {unrecorded} row(s) are recorded nowhere else. "
            f"Run --export first, or pass --force to delete them anyway."
        )
        return 1

    table_dir = Path(uri) / "archival_memories.lance"
    if table_dir.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = table_dir.with_name(f"archival_memories.backup-{stamp}.lance")
        print(f"\nbacking up {table_dir.name} -> {backup.name} ...", flush=True)
        shutil.copytree(table_dir, backup)
    else:
        print(
            f"\nWARNING: no table directory at {table_dir}; deleting without a backup"
        )

    ids = [r["id"] for r in legacy if r.get("id")]
    deleted = 0
    for i in range(0, len(ids), 200):
        chunk = ids[i : i + 200]
        quoted = ", ".join("'" + str(x).replace("'", "''") + "'" for x in chunk)
        await store.archival_table.delete(f"id IN ({quoted})")
        deleted += len(chunk)
        print(f"  deleted {deleted}/{len(ids)}", flush=True)

    if hasattr(store, "optimize"):
        await store.optimize()
    print(f"\nretired {deleted} legacy row(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--uri", default=None, help="LanceDB path (default: configured)")
    ap.add_argument("--apply", action="store_true", help="actually delete the rows")
    ap.add_argument("--sample", type=int, default=5, help="example rows to print")
    ap.add_argument(
        "--export",
        nargs="?",
        const=True,
        default=None,
        metavar="ARCHIVE_DIR",
        help="append the rows to daily logs (default: the configured archive dir)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="delete even rows that are recorded nowhere else",
    )
    args = ap.parse_args()

    if os.environ.get("SUZENT_DATA_DIR"):
        print(f"SUZENT_DATA_DIR={os.environ['SUZENT_DATA_DIR']}")

    if args.export is True:
        from suzent.config import CONFIG

        args.export = Path(CONFIG.sandbox_data_path) / "shared" / "memory" / "archive"
    elif args.export:
        args.export = Path(args.export)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
