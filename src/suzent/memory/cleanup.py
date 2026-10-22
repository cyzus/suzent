"""One-time cleanup of memory written before the map, capture and judgment existed.

Fixing the pipeline does not repair what is already in the vault and the core files.
This module never edits them: it writes drafts, diffs and a brief into
`.state/cleanup/<date>/`, and the user decides what to apply. The steps follow the
design's §5: a pointer map to replace MEMORY.md, the non-contract lines of `user.md`
moved out, what `user.md` owns removed from the vault pages, a rewrite brief for
the pages, and claims already known to be wrong seeded into the rejected list.
See docs/08-developing/architecture/memory-architecture.md.
"""

import difflib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from suzent.logger import get_logger
from suzent.memory import capture, memory_map
from suzent.memory.markdown_store import MarkdownMemoryStore

logger = get_logger(__name__)

# Claims the user has already said are wrong, with why, for the rejected list.
SEED_REJECTED: tuple[tuple[str, str], ...] = (
    (
        "The Perfect Drone",
        "a story the agent wrote, recorded as the user's own project",
    ),
)
# A page bullet this close to a user.md line repeats what user.md owns.
DUPLICATE_MATCH = 0.9

_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")


@dataclass
class CleanupResult:
    out_dir: Path
    files: list[Path] = field(default_factory=list)
    moved_lines: int = 0
    findings: int = 0


def _diff(name: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{name}",
            tofile=f"b/{name}",
        )
    )


def _is_fact_line(line: str) -> bool:
    """A line of an old MEMORY.md that says something, not a heading or marker."""
    s = line.strip()
    return bool(s) and not s.startswith(("#", "<!--", "*Last updated"))


def draft_memory_map(
    current: str, vault: Path, pages: list[Path]
) -> tuple[str, list[str]]:
    """The map to replace MEMORY.md, and the lines of the old file that held facts.

    An old summary is replaced whole by a draft from page titles. A file that is
    already a map keeps the user's pointer lines in their order; only lines without a
    link leave it, and pages with no line yet are appended.
    """
    generated = memory_map.draft_map(vault, pages)
    if not memory_map.is_map(current):
        return generated, [
            ln.strip() for ln in current.splitlines() if _is_fact_line(ln)
        ]

    entries = memory_map.parse_map(current)
    moved = [e.raw.strip() for e in entries if not e.link]
    moved_lines = {e.lineno for e in entries if not e.link}
    kept = [ln for i, ln in enumerate(current.splitlines(), 1) if i not in moved_lines]
    links = {e.link for e in entries if e.link}
    added = [
        e.raw for e in memory_map.parse_map(generated) if e.link and e.link not in links
    ]
    text = "\n".join(kept).rstrip() + "\n"
    if added:
        text += "\n".join(added) + "\n"
    return text, moved


def draft_user_md(text: str, rejected: list[str]) -> tuple[str, list[str]]:
    """`user.md` without the lines its contract excludes, and those lines."""
    kept: list[str] = []
    moved: list[str] = []
    for line in text.splitlines():
        if line.strip() and (
            memory_map.line_issue(line) or memory_map.matches_rejected(line, rejected)
        ):
            moved.append(line.strip())
        else:
            kept.append(line)
    return "\n".join(kept).rstrip() + "\n", moved


def draft_page(page: str, user_md: str) -> tuple[str, list[str]]:
    """A vault page without the bullets `user.md` already holds."""
    owned = [
        capture.normalize(m.group(1))
        for m in map(_BULLET.match, user_md.splitlines())
        if m
    ]
    kept: list[str] = []
    removed: list[str] = []
    for line in page.splitlines():
        m = _BULLET.match(line)
        body = capture.normalize(m.group(1)) if m else ""
        if body and any(capture.similarity(body, o) >= DUPLICATE_MATCH for o in owned):
            removed.append(line.strip())
        else:
            kept.append(line)
    return "\n".join(kept).rstrip() + "\n", removed


def _page_notes(store: MarkdownMemoryStore, rejected: list[str]) -> list[str]:
    """What the rewrite has to look at, page by page.

    Pages are judged by their declared `type:`, never their folder. Only personal
    pages get the repo-state and scheduler checks: a wiki page may cite a version.
    """
    vault = store.notebook_dir
    notes: list[str] = []
    for page in store.list_notebook_pages():
        rel = page.relative_to(vault).as_posix()
        try:
            text = page.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        personal = memory_map.page_type(text) == memory_map.PERSONAL_TYPE
        issues: list[str] = []
        size = len(text.encode("utf-8"))
        if size > memory_map.PAGE_BUDGET_BYTES:
            issues.append(
                f"{size // 1024} KB, over the {memory_map.PAGE_BUDGET_BYTES // 1024} KB "
                "budget: condense, or split by topic"
            )
        if not memory_map.page_type(text):
            issues.append("no `type:` in frontmatter: add one from schema.md")
        for i, line in enumerate(text.splitlines(), 1):
            code = memory_map.line_issue(line) if personal else None
            hit = memory_map.matches_rejected(line, rejected)
            if hit:
                issues.append(f"line {i} holds rejected claim {hit!r}: retire it")
            elif code:
                issues.append(f"line {i} looks like {code}: retire it")
        if issues:
            notes.append(f"### {rel}\n" + "\n".join(f"- {s}" for s in issues))
    return notes


_REWRITE_RULES = """\
## Rules
- Each fact has one home. Facts in `user.md` are not repeated in the vault.
- Every page declares a `type:` from `schema.md`; facts about the user go on
  `type: personal` pages. `schema.md` decides which folder each type lives in.
- Keep the current value in the bullet. Move a superseded value to the page's
  `## History` section, or drop it when it never mattered.
- Retire bullets that are repo state (PRs, commits, versions, branches), transient
  status, scheduler specs or analyses the agent wrote. Retiring is allowed.
- Something the agent made, proposed or designed is not the user's: move it off
  the personal pages to an experience page (a lesson with its outcome) or a
  knowledge page (with its source), or retire it.
- A contradiction you cannot settle becomes a question in
  `.state/review_queue.md`, not a callout on the page.
- Counters go to frontmatter (`confirmed: 12`); a bullet carries at most one
  "last confirmed" date.
- Keep each page under 8 KB; split a page by topic when it is over.
- Every page you create, retire or rename gets its `MEMORY.md` line fixed in the
  same step.
- Record each operation in `.state/dream_ops.md` with the text before and after."""


def rewrite_brief(
    moved: dict[str, list[str]], page_notes: list[str], rejected: list[str]
) -> str:
    parts = [
        "# Memory rewrite brief",
        "",
        "A one-off pass over the vault pages, run once the drafts in this "
        "folder are applied. Give it to the dream agent or work through it by hand.",
        "",
        _REWRITE_RULES,
        "",
        "## Lines taken out of the core files",
        "File each into the page it belongs to, or drop it if a rule above excludes it.",
    ]
    for source, lines in moved.items():
        if lines:
            parts += [
                "",
                f"### From {source}",
                *(f"- {ln.lstrip('-*+ ')}" for ln in lines),
            ]
    if not any(moved.values()):
        parts.append("(none)")
    parts += ["", "## Pages", *(page_notes or ["(nothing flagged)"])]
    parts += ["", "## Rejected claims", "Retire any bullet that restates one of these."]
    parts += [f"- {r}" for r in rejected] or ["(none)"]
    return "\n".join(parts) + "\n"


_README = """\
# Memory cleanup drafts ({date})

Nothing outside this folder was changed. Review each file, edit it if needed, then
apply what you accept.

| File | What it is | To apply |
|---|---|---|
| `MEMORY.draft.md` | The pointer map to replace `MEMORY.md` | copy over `{memory_md}` |
| `user.draft.md` | `user.md` without scheduler specs, repo state and rejected claims | copy over `{user_md}` |
| `pages/` | Vault pages without what `user.md` already holds | copy each over the page at the same path |
| `migration.diff` | All of these changes as one diff | read it before copying |
| `rewrite_brief.md` | Where the moved lines go, and what to fix page by page | ask the agent to work through it |
| `rejected.seed.jsonl` | Claims already known to be wrong | append to `{rejected}` |

## Lint before cleanup
{findings}
"""


async def write_cleanup_drafts(
    store: MarkdownMemoryStore,
    *,
    max_lines: int = memory_map.DEFAULT_MAP_MAX_LINES,
    date: Optional[str] = None,
) -> CleanupResult:
    """Write the cleanup drafts for *store*; never touches a live file."""
    date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = store.notebook_state_dir / "cleanup" / date
    out.mkdir(parents=True, exist_ok=True)
    result = CleanupResult(out_dir=out)
    vault = store.notebook_dir
    pages = store.list_notebook_pages()
    rejected = store.read_rejected()
    findings = await memory_map.lint_store(store, max_lines=max_lines)
    result.findings = len(findings)

    memory_md = await store.read_memory_file() or ""
    user_md = await store.read_block("user") or ""

    seeds = [
        {"content": claim, "date": date, "correction_id": "", "reason": reason}
        for claim, reason in SEED_REJECTED
        if not store.is_rejected(claim, rejected)
    ]
    all_rejected = rejected + [s["content"] for s in seeds]

    map_draft, from_map = draft_memory_map(memory_md, vault, pages)
    user_draft, from_user = (
        draft_user_md(user_md, all_rejected) if user_md else ("", [])
    )
    page_drafts: dict[str, tuple[str, str]] = {}
    for page in pages if user_md else []:
        try:
            before = page.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        after, removed = draft_page(before, user_md)
        if removed:
            page_drafts[page.relative_to(vault).as_posix()] = (before, after)
    result.moved_lines = len(from_map) + len(from_user)

    drafts: dict[str, str] = {"MEMORY.draft.md": map_draft}
    if user_md:
        drafts["user.draft.md"] = user_draft
    for rel, (_, after) in page_drafts.items():
        drafts[f"pages/{rel}"] = after
    drafts["migration.diff"] = (
        _diff("MEMORY.md", memory_md, map_draft)
        + (_diff("user.md", user_md, user_draft) if user_md else "")
        + "".join(_diff(rel, b, a) for rel, (b, a) in page_drafts.items())
    )
    drafts["rewrite_brief.md"] = rewrite_brief(
        {"MEMORY.md": from_map, "user.md": from_user},
        _page_notes(store, all_rejected),
        all_rejected,
    )
    drafts["rejected.seed.jsonl"] = "".join(
        json.dumps(s, ensure_ascii=False) + "\n" for s in seeds
    )
    drafts["README.md"] = _README.format(
        date=date,
        memory_md=store.memory_file_path,
        user_md=store.base_dir / "user.md",
        rejected=store.rejected_path,
        findings=memory_map.format_findings(findings, limit=100),
    )

    for name, text in drafts.items():
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        result.files.append(path)
    logger.info(
        f"Wrote memory cleanup drafts to {out}: {result.moved_lines} line(s) to move, "
        f"{result.findings} lint finding(s)"
    )
    return result
