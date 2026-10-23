"""MEMORY.md as a curated map of the vault, and the lint that keeps it honest.

MEMORY.md used to be an LLM summary of the personal pages plus a hand-edited zone.
Both held facts, so every fact had two or three copies that drifted apart and nothing
checked the hand-edited half. The map holds only pointers: one line per page or folder
worth knowing about, saying what it holds and when to read it. The dream and the user
write it; this module only parses, checks and, when the file is missing, drafts it.

The same module checks the other always-injected files (`user.md`, `persona.md`,
`heartbeat.md`) against their contracts, since both checks feed the same dream brief.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Literal, Optional

if TYPE_CHECKING:
    from suzent.memory.markdown_store import MarkdownMemoryStore

MAP_HEADING = "# Memory map"
DEFAULT_MAP_MAX_LINES = 30
# A map line says what a page holds and when to read it; past this it is carrying the
# content itself.
MAP_LINE_MAX_CHARS = 200
USER_MD_MAX_LINES = 40
PERSONA_MD_MAX_LINES = 60
PAGE_BUDGET_BYTES = 8 * 1024
# Pages are found by the `type:` they declare, not by folder: users rename and
# renumber folders, and placement is the notebook skill's call, not the code's.
PERSONAL_TYPE = "personal"

# Pre-map MEMORY.md files: the zone markers and the footer of the old generator.
_LEGACY_MARKERS = (
    "<!-- memory:generated",
    "<!-- /memory:generated",
)
_LEGACY_FOOTER_RE = re.compile(r"^\*Last updated: .*UTC\*\s*$", re.MULTILINE)

_LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_COUNTER_RE = re.compile(r"\b(?:confirmed\s+\d+x|\d+x\b|\d+\s+times\b)", re.IGNORECASE)
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_TYPE_RE = re.compile(r"^type\s*:\s*(.+?)\s*$", re.MULTILINE)

FindingCode = Literal[
    "not_a_map",
    "unresolved_link",
    "not_a_pointer",
    "rejected_match",
    "missing_line",
    "stale_line",
    "over_cap",
    "over_budget",
    "scheduler_spec",
    "repo_state",
    "untyped",
]


@dataclass(frozen=True)
class MapLine:
    lineno: int
    raw: str
    link: Optional[str]
    description: str


@dataclass(frozen=True)
class Finding:
    file: str
    code: FindingCode
    detail: str
    line: Optional[int] = None

    def render(self) -> str:
        where = f"{self.file}:{self.line}" if self.line else self.file
        return f"- [{self.code}] {where} — {self.detail}"


def page_type(text: str) -> str:
    """The `type:` a page declares in its frontmatter, lowercased, or ""."""
    fm = _FRONTMATTER_RE.match(text)
    m = _TYPE_RE.search(fm.group(1)) if fm else None
    return m.group(1).strip().strip("\"'").lower() if m else ""


def read_page_type(page: Path) -> str:
    try:
        return page_type(page.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return ""


def is_legacy(text: str) -> bool:
    """True for a MEMORY.md written by the old summariser (zones or its footer)."""
    return any(m in text for m in _LEGACY_MARKERS) or bool(
        _LEGACY_FOOTER_RE.search(text)
    )


def parse_map(text: str) -> list[MapLine]:
    """Every bullet in the file, with its first wiki link if it has one."""
    lines: list[MapLine] = []
    for i, raw in enumerate(text.splitlines(), 1):
        m = _BULLET_RE.match(raw)
        if not m:
            continue
        body = m.group(1).strip()
        link = _LINK_RE.search(body)
        desc = _LINK_RE.sub("", body).strip(" —-:;\t")
        lines.append(MapLine(i, raw, link.group(1).strip() if link else None, desc))
    return lines


def is_map(text: str) -> bool:
    """Whether *text* is a pointer map rather than an older summary or free notes."""
    if not text.strip() or is_legacy(text):
        return False
    return any(line.link for line in parse_map(text))


def resolve_link(link: str, vault: Path) -> Optional[Path]:
    """The page or folder a map link points at, or None.

    Accepts `folder/`, `path/Page`, `path/Page.md` and, as Obsidian does, a bare page
    name that is unique in the vault.
    """
    target = link.strip().strip("/")
    if not target:
        return None
    candidate = vault / target
    if candidate.is_dir():
        return candidate
    page = (
        candidate
        if candidate.suffix == ".md"
        else candidate.with_name(candidate.name + ".md")
    )
    if page.is_file():
        return page
    if "/" not in target:
        name = target if target.endswith(".md") else f"{target}.md"
        hits = [p for p in vault.rglob(name) if ".state" not in p.parts]
        if len(hits) == 1:
            return hits[0]
    return None


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def matches_rejected(text: str, rejected: Iterable[str]) -> Optional[str]:
    """The rejected claim *text* contains, if any (normalized substring)."""
    body = _normalize(text)
    for claim in rejected:
        key = _normalize(claim)
        if key and key in body:
            return claim
    return None


def _covers(resolved: Path, page: Path) -> bool:
    return resolved == page or (resolved.is_dir() and resolved in page.parents)


def lint_map(
    text: Optional[str],
    vault: Path,
    pages: list[Path],
    *,
    rejected: Iterable[str] = (),
    recalled_files: Optional[set[str]] = None,
    max_lines: int = DEFAULT_MAP_MAX_LINES,
) -> list[Finding]:
    """Check MEMORY.md against the map contract (design §4.5).

    *recalled_files* is the set of vault-relative paths retrieval has returned lately.
    It only ever produces a suggestion: ranking the map by recall would keep whatever
    is already listed, because it is read because it is listed.
    """
    name = "MEMORY.md"
    if text is None or not is_map(text):
        return [
            Finding(
                name,
                "not_a_map",
                "not a pointer map yet; rewrite it as `- [[page]] — holds …; read when …` lines",
            )
        ]
    rejected = list(rejected)
    findings: list[Finding] = []
    entries = parse_map(text)
    resolved: list[Path] = []
    for entry in entries:
        if entry.link is None:
            findings.append(
                Finding(name, "not_a_pointer", "line has no [[link]]", entry.lineno)
            )
        else:
            target = resolve_link(entry.link, vault)
            if target is None:
                findings.append(
                    Finding(
                        name,
                        "unresolved_link",
                        f"[[{entry.link}]] does not resolve",
                        entry.lineno,
                    )
                )
            else:
                resolved.append(target)
                if (
                    recalled_files is not None
                    and target.is_file()
                    and target.relative_to(vault).as_posix() not in recalled_files
                ):
                    findings.append(
                        Finding(
                            name,
                            "stale_line",
                            f"[[{entry.link}]] has not been recalled lately; consider a folder line instead (suggestion only)",
                            entry.lineno,
                        )
                    )
        if (
            _DATE_RE.search(entry.description)
            or _COUNTER_RE.search(entry.description)
            or len(entry.description) > MAP_LINE_MAX_CHARS
        ):
            findings.append(
                Finding(
                    name,
                    "not_a_pointer",
                    "line carries dates, counters or content; move the fact into the page",
                    entry.lineno,
                )
            )
        hit = matches_rejected(entry.raw, rejected)
        if hit:
            findings.append(
                Finding(
                    name,
                    "rejected_match",
                    f"contains rejected claim {hit!r}",
                    entry.lineno,
                )
            )

    top_folders = {
        vault / p.relative_to(vault).parts[0]
        for p in pages
        if len(p.relative_to(vault).parts) > 1
    }
    for folder in sorted(top_folders):
        if not any(r == folder or folder in r.parents for r in resolved):
            findings.append(
                Finding(
                    name,
                    "missing_line",
                    f"top-level folder {folder.name}/ has no line",
                )
            )
    for page in pages:
        if read_page_type(page) != PERSONAL_TYPE:
            continue
        rel = page.relative_to(vault)
        if not any(_covers(r, page) for r in resolved):
            findings.append(
                Finding(
                    name,
                    "missing_line",
                    f"{rel.as_posix()} has no line and no folder line covers it",
                )
            )

    if len(entries) > max_lines:
        findings.append(
            Finding(
                name,
                "over_cap",
                f"{len(entries)} lines (cap {max_lines}); merge page lines into folder lines",
            )
        )
    return findings


_SCHEDULER_RE = re.compile(
    r"(\bcron\b|\bevery (day|morning|evening|week|hour)\b|\bdaily at\b|"
    r"\bscheduled task\b|每天|每日|每周|定时|\b\d{1,2}:\d{2}\s*(am|pm)?\b.*\b(remind|send|post|report)\b)",
    re.IGNORECASE,
)
_REPO_STATE_RE = re.compile(
    r"(\bPR\s*#\d+|\bpull request #?\d+|\b(issue|ticket) #\d+|\bcommit [0-9a-f]{7,40}\b|"
    r"\bv\d+\.\d+\.\d+\b|\bbranch [\w./-]+|\b[0-9a-f]{12,40}\b)",
    re.IGNORECASE,
)
_LINE_ISSUE_DETAIL: dict[str, str] = {
    "scheduler_spec": "looks like a scheduled-task spec; it belongs to the scheduler",
    "repo_state": "looks like repo state (PR, commit, version, branch); the repo already holds it",
}


def line_issue(line: str) -> Optional[FindingCode]:
    """Why a line belongs somewhere other than memory, if it does."""
    if _SCHEDULER_RE.search(line):
        return "scheduler_spec"
    if _REPO_STATE_RE.search(line):
        return "repo_state"
    return None


def lint_contract(
    label: str, text: Optional[str], *, rejected: Iterable[str] = ()
) -> list[Finding]:
    """Check an always-injected file against its contract (design §4.5).

    `user.md` holds what the agent needs on every turn; scheduler specs belong to the
    scheduler and repo state to the repo. `persona.md` only gets the size cap.
    `heartbeat.md` holds protocol, so any rejected claim in it is a leak.
    """
    if not text:
        return []
    name = f"{label}.md"
    findings: list[Finding] = []
    lines = text.splitlines()
    cap = {"user": USER_MD_MAX_LINES, "persona": PERSONA_MD_MAX_LINES}.get(label)
    content_lines = [ln for ln in lines if ln.strip()]
    if cap and len(content_lines) > cap:
        findings.append(
            Finding(
                name,
                "over_cap",
                f"{len(content_lines)} non-empty lines (cap {cap}); move detail into vault pages",
            )
        )
    for i, line in enumerate(lines, 1):
        code = line_issue(line) if label == "user" else None
        if code:
            findings.append(Finding(name, code, _LINE_ISSUE_DETAIL[code], i))
        hit = matches_rejected(line, rejected)
        if hit:
            findings.append(
                Finding(name, "rejected_match", f"contains rejected claim {hit!r}", i)
            )
    return findings


def lint_page_budgets(
    vault: Path, pages: list[Path], budget: int = PAGE_BUDGET_BYTES
) -> list[Finding]:
    """Pages over the size budget, which the dream condenses or splits."""
    out: list[Finding] = []
    for page in pages:
        try:
            size = page.stat().st_size
        except OSError:
            continue
        if size > budget:
            out.append(
                Finding(
                    page.relative_to(vault).as_posix(),
                    "over_budget",
                    f"{size // 1024} KB (budget {budget // 1024} KB); condense or split",
                )
            )
    return out


def lint_page_types(vault: Path, pages: list[Path], shown: int = 5) -> list[Finding]:
    """One finding for all pages without a `type:`, which the checks above cannot see."""
    untyped = [
        page.relative_to(vault).as_posix() for page in pages if not read_page_type(page)
    ]
    if not untyped:
        return []
    names = ", ".join(untyped[:shown]) + (" …" if len(untyped) > shown else "")
    return [
        Finding(
            "vault",
            "untyped",
            f"{len(untyped)} page(s) have no `type:` in frontmatter; give each one "
            f"({names})",
        )
    ]


def _page_title(page: Path) -> tuple[str, str]:
    """The page's title and its first `##` headings, from frontmatter or headings."""
    try:
        text = page.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return page.stem, ""
    title = page.stem
    fm = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if fm:
        t = re.search(r"^title\s*:\s*(.+)$", fm.group(1), re.MULTILINE)
        if t:
            title = t.group(1).strip().strip("\"'")
    h1 = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if h1 and not fm:
        title = h1.group(1).strip()
    sections = re.findall(r"^##\s+(.+)$", text, re.MULTILINE)
    sections = [s.strip() for s in sections if s.strip().lower() != "related"][:4]
    return title, ", ".join(sections)


def draft_map(vault: Path, pages: list[Path]) -> str:
    """A starting map built from titles and headings, for when MEMORY.md is missing.

    One line per personal page and one per top-level folder holding the rest. It is
    a fallback only: the dream rewrites it on its next run and the user can edit it.
    """
    lines = [MAP_HEADING, ""]
    folders: dict[str, int] = {}
    for page in pages:
        rel = page.relative_to(vault)
        if read_page_type(page) == PERSONAL_TYPE:
            title, sections = _page_title(page)
            link = rel.with_suffix("").as_posix()
            holds = f"holds {sections}" if sections else f"holds {title}"
            lines.append(
                f"- [[{link}]] — {holds}; read when the user's {title.lower()} matters"
            )
        elif len(rel.parts) > 1:
            folders[rel.parts[0]] = folders.get(rel.parts[0], 0) + 1
    for top, count in sorted(folders.items()):
        lines.append(
            f"- [[{top}/]] — {count} page(s); read before answering from memory about anything filed here"
        )
    return "\n".join(lines) + "\n"


def format_findings(findings: list[Finding], limit: int = 40) -> str:
    """Render findings for the dream brief, or a placeholder when there are none."""
    if not findings:
        return "   (none)"
    shown = [f"   {f.render()}" for f in findings[:limit]]
    if len(findings) > limit:
        shown.append(f"   … and {len(findings) - limit} more")
    return "\n".join(shown)


async def lint_store(store: "MarkdownMemoryStore", *, max_lines: int) -> list[Finding]:
    """Contract findings for MEMORY.md, the always-injected files and page sizes."""
    vault = store.notebook_dir
    pages = store.list_notebook_pages()
    rejected = store.read_rejected()
    findings = lint_map(
        await store.read_memory_file(),
        vault,
        pages,
        rejected=rejected,
        recalled_files=store.recalled_files(),
        max_lines=max_lines,
    )
    for label in ("user", "persona", "heartbeat"):
        findings += lint_contract(
            label, await store.read_block(label), rejected=rejected
        )
    findings += lint_page_budgets(vault, pages)
    findings += lint_page_types(vault, pages)
    return findings
