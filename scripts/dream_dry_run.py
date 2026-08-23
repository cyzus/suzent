"""Run the catch-up dream against a *copy* of the user's data directory.

The backlog is five months of daily logs. Consolidating it is the first step in this
work that mutates live memory: the agent rewrites vault pages and retires archival rows,
and a bad `superseded.txt` line costs real facts. That is not something to try for the
first time on the only copy of someone's memory.

This script clones `~/.suzent` into a scratch directory, points the whole app at the
clone through `SUZENT_DATA_DIR`, drives the real `DreamRunner` over it, and prints a
reviewable diff of what the dream did to the vault.

    python scripts/dream_dry_run.py --cycles 1
    python scripts/dream_dry_run.py --cycles 30 --keep

Nothing here writes to the real data directory. The clone is created fresh each run
unless `--target` names an existing one, and the LLM calls are real — a full backlog
pass is many agent runs and costs real money and hours, which is why `--cycles`
defaults to 1.
"""

import argparse
import asyncio
import difflib
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Everything the app reads is derived from SUZENT_DATA_DIR at import time, so the
# override has to be in place before any suzent module is imported.
REPO_ROOT = Path(__file__).resolve().parent.parent


# What the dream actually touches. Deliberately not the whole data directory:
# `chats.db` alone is ~560MB of conversation history the dream never reads, and
# copying it would dominate the run.
CLONE_ALWAYS = (
    "notebook",
    "sandbox",
    "config",
    "skills",
    "capabilities",
    ".secret_key",
)

# The LanceDB index (~800MB). The ingest phase reads markdown, not the index — the
# index only matters for observing the reindex that follows. Skippable for a fast pass.
CLONE_INDEX = "memory"


def clone_data_dir(source: Path, target: Path, with_index: bool) -> Path:
    """Copy the parts of the data dir the dream reads or writes."""
    if target.exists():
        print(f"reusing existing clone at {target}")
        return target

    target.mkdir(parents=True)
    names = list(CLONE_ALWAYS) + ([CLONE_INDEX] if with_index else [])
    for name in names:
        src = source / name
        if not src.exists():
            continue
        dst = target / name
        print(f"  copying {name} ...", flush=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    return target


def redirect_notebook_volume(target: Path) -> Path:
    """Point the clone's `/mnt/notebook` mapping at a copy of the real vault.

    This is the trap the whole script exists to catch. The vault is usually NOT inside
    the data directory — it is a host path mounted at `/mnt/notebook` (here, a folder
    under OneDrive), so cloning `~/.suzent` alone isolates everything *except* the one
    thing the dream rewrites. Without this redirect a "dry run" edits the real vault.

    Returns the path the dry run's vault now lives at.
    """
    cfg_path = target / "config" / "local.yaml"
    fallback = target / "notebook"
    if not cfg_path.exists():
        return fallback

    text = cfg_path.read_text(encoding="utf-8")
    m = re.search(r"^(\s*-\s*)(.+?):(/mnt/notebook)\s*$", text, re.MULTILINE)
    if not m:
        return fallback

    real_vault = Path(m.group(2))
    clone_vault = target / "notebook-vault"
    if real_vault.exists() and not clone_vault.exists():
        print(f"  copying vault {real_vault} ...", flush=True)
        shutil.copytree(real_vault, clone_vault)
    clone_vault.mkdir(parents=True, exist_ok=True)

    text = text.replace(m.group(0), f"{m.group(1)}{clone_vault}:/mnt/notebook")
    # notebook_dir is the non-sandbox fallback for the same vault; keep them agreed.
    if re.search(r"^notebook_dir:", text, re.MULTILINE):
        text = re.sub(
            r"^notebook_dir:.*$",
            f"notebook_dir: {clone_vault}",
            text,
            flags=re.MULTILINE,
        )
    else:
        text += f"\nnotebook_dir: {clone_vault}\n"
    cfg_path.write_text(text, encoding="utf-8")
    print(f"  vault redirected to {clone_vault}")
    return clone_vault


def snapshot_vault(notebook: Path) -> dict:
    """Path → text for every page in the vault, so the run can be diffed."""
    pages = {}
    for p in sorted(notebook.rglob("*.md")):
        if ".state" in p.parts:
            continue
        try:
            pages[p.relative_to(notebook).as_posix()] = p.read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            continue
    return pages


def render_diff(before: dict, after: dict) -> str:
    out = []
    for name in sorted(set(before) | set(after)):
        old = before.get(name, "").splitlines(keepends=True)
        new = after.get(name, "").splitlines(keepends=True)
        if old == new:
            continue
        out.extend(
            difflib.unified_diff(old, new, fromfile=f"a/{name}", tofile=f"b/{name}")
        )
    return "".join(out) or "(no page changes)\n"


async def drive(cycles: int) -> list[dict]:
    """Run the real DreamRunner over the clone, one forced ingest per cycle.

    The memory stack is booted through the app's own initializer rather than
    hand-assembled, so the dry run exercises the same wiring the product does --
    including model routing, the vault bootstrap, and the background watcher.
    """
    from suzent.core.dream_runner import DreamRunner
    from suzent.memory.lifecycle import init_memory_system

    if not await init_memory_system():
        print("memory system failed to initialize (is memory_enabled set?)")
        return []

    runner = DreamRunner()
    results = []
    for i in range(1, cycles + 1):
        print(f"\n--- cycle {i}/{cycles} ---", flush=True)
        result = await runner.force_run()
        print(
            f"  ran={result.get('ran')} advanced={result.get('advanced')} "
            f"watermark={result.get('watermark')} "
            f"reason={result.get('reason') or result.get('summary', '')[:120]}",
            flush=True,
        )
        results.append(result)
        if not result.get("advanced"):
            print("  watermark did not advance; stopping early", flush=True)
            break
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cycles", type=int, default=1, help="forced ingest runs")
    ap.add_argument("--source", type=Path, default=Path.home() / ".suzent")
    ap.add_argument("--target", type=Path, default=None, help="clone location")
    ap.add_argument("--keep", action="store_true", help="do not delete the clone")
    ap.add_argument(
        "--skip-index",
        action="store_true",
        help="do not copy the ~800MB LanceDB index (ingest does not read it)",
    )
    args = ap.parse_args()

    if not args.source.exists():
        print(f"no data directory at {args.source}", file=sys.stderr)
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = args.target or Path(tempfile.gettempdir()) / f"suzent-dream-{stamp}"

    print(f"cloning {args.source} -> {target}")
    clone_data_dir(args.source, target, with_index=not args.skip_index)

    os.environ["SUZENT_DATA_DIR"] = str(target)
    sys.path.insert(0, str(REPO_ROOT / "src"))

    notebook = redirect_notebook_volume(target)
    before = snapshot_vault(notebook)
    print(f"vault before: {len(before)} pages")

    try:
        results = asyncio.run(drive(args.cycles))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        results = []

    after = snapshot_vault(notebook)
    diff = render_diff(before, after)

    report = target / "dry-run-report.diff"
    report.write_text(diff, encoding="utf-8")

    print(f"\nvault after: {len(after)} pages ({len(after) - len(before):+d})")
    print(f"cycles that advanced: {sum(1 for r in results if r.get('advanced'))}")
    print(f"diff written to {report}")

    if not args.keep and args.target is None:
        print(f"clone left at {target} (use --keep to silence this note)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
