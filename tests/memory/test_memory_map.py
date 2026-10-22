"""MEMORY.md is a curated map of the vault, not a generated summary.

The old file was rewritten by two summarisers and grew stale claims nobody could trace
to a page. The map holds one pointer per page or folder; facts live in the pages, and
lint checks every line the same way whoever wrote it.
"""

import pytest

from suzent.memory import memory_context, memory_map
from suzent.memory.indexer import CoreMemoryFileIndexer
from suzent.memory.markdown_store import MarkdownMemoryStore


@pytest.fixture
def store(tmp_path):
    return MarkdownMemoryStore(
        base_dir=tmp_path, notebook_dir=str(tmp_path / "notebook")
    )


def _page(store: MarkdownMemoryStore, rel: str, body: str = "# Page\n") -> None:
    path = store.notebook_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _codes(findings) -> list[str]:
    return [f.code for f in findings]


# --- parsing ---


def test_a_legacy_summary_is_not_a_map():
    legacy = "# Long-term Memory\n<!-- memory:generated -->\n- [[x]] a fact\n"
    assert memory_map.is_legacy(legacy)
    assert not memory_map.is_map(legacy)
    assert not memory_map.is_map("- just a note with no link\n")
    assert memory_map.is_map("# Memory map\n\n- [[3_Personal/Identity]] — holds name\n")


def test_links_resolve_to_folders_pages_and_unique_bare_names(store):
    _page(store, "3_Personal/Identity.md")
    _page(store, "2_Wiki/Rust.md")
    vault = store.notebook_dir

    assert memory_map.resolve_link("2_Wiki/", vault) == vault / "2_Wiki"
    assert memory_map.resolve_link("3_Personal/Identity", vault).name == "Identity.md"
    assert memory_map.resolve_link("Rust", vault) == vault / "2_Wiki" / "Rust.md"
    assert memory_map.resolve_link("Nowhere", vault) is None


# --- lint ---


def test_lint_reports_what_a_map_line_must_not_be(store):
    _page(store, "3_Personal/Identity.md")
    _page(store, "3_Personal/Health.md", "---\ntype: personal\n---\n")
    _page(store, "2_Wiki/Rust.md")
    text = (
        "# Memory map\n\n"
        "- [[3_Personal/Identity]] — holds name; confirmed 12x on 2026-10-01\n"
        "- [[Gone]] — holds nothing\n"
        "- a bare note without a link\n"
        "- [[2_Wiki/]] — knowledge pages; mentions The Perfect Drone\n"
    )

    findings = memory_map.lint_map(
        text,
        store.notebook_dir,
        store.list_notebook_pages(),
        rejected=["The Perfect Drone"],
    )
    codes = _codes(findings)

    assert "unresolved_link" in codes
    assert codes.count("not_a_pointer") == 2
    assert "rejected_match" in codes
    missing = [f.detail for f in findings if f.code == "missing_line"]
    assert missing == ["3_Personal/Health.md has no line and no folder line covers it"]


def test_a_folder_line_covers_every_page_under_it(store):
    _page(store, "3_Personal/Identity.md")
    _page(store, "3_Personal/sub/Health.md")
    text = "# Memory map\n\n- [[3_Personal/]] — who the user is; read when it matters\n"

    findings = memory_map.lint_map(
        text, store.notebook_dir, store.list_notebook_pages()
    )

    assert findings == []


def test_an_old_summary_gets_one_finding_not_dozens(store):
    findings = memory_map.lint_map(
        "# Long-term Memory\n\n- Prefers dark mode\n",
        store.notebook_dir,
        store.list_notebook_pages(),
    )
    assert _codes(findings) == ["not_a_map"]


def test_over_cap_and_recall_suggestions(store):
    for i in range(4):
        _page(store, f"3_Personal/P{i}.md")
    lines = "\n".join(
        f"- [[3_Personal/P{i}]] — holds p{i}; read when p{i}" for i in range(4)
    )
    findings = memory_map.lint_map(
        "# Memory map\n\n" + lines,
        store.notebook_dir,
        store.list_notebook_pages(),
        recalled_files={"3_Personal/P0.md"},
        max_lines=3,
    )
    codes = _codes(findings)

    assert "over_cap" in codes
    assert codes.count("stale_line") == 3


def test_the_draft_map_passes_its_own_lint(store):
    _page(
        store,
        "3_Personal/Identity.md",
        "---\ntitle: Identity\ntype: personal\n---\n## Name\n",
    )
    # Found by its type, in a folder the user named themselves.
    _page(store, "About me/Work.md", "---\ntype: personal\n---\n## Role\n## Team\n")
    _page(store, "2_Wiki/Rust.md")
    _page(store, "1_Projects/suzent/Plan.md")
    pages = store.list_notebook_pages()

    draft = memory_map.draft_map(store.notebook_dir, pages)

    assert draft.startswith(memory_map.MAP_HEADING)
    assert "[[3_Personal/Identity]] — holds Name;" in draft
    assert "[[About me/Work]] — holds Role, Team;" in draft
    assert "[[2_Wiki/]]" in draft and "[[1_Projects/]]" in draft
    assert memory_map.lint_map(draft, store.notebook_dir, pages) == []


def test_untyped_pages_are_one_finding(store):
    _page(store, "3_Personal/Identity.md", "# Identity\n")
    _page(store, "2_Wiki/Rust.md", "---\ntype: concept\n---\n")

    findings = memory_map.lint_page_types(
        store.notebook_dir, store.list_notebook_pages()
    )

    assert _codes(findings) == ["untyped"]
    assert "1 page(s)" in findings[0].detail
    assert "3_Personal/Identity.md" in findings[0].detail


def test_user_md_contract():
    text = (
        "- Name: Sam\n- Every morning at 9:00 send the news report\n- PR #398 merged\n"
    )
    codes = _codes(memory_map.lint_contract("user", text))
    assert codes == ["scheduler_spec", "repo_state"]

    long = "\n".join(f"- line {i}" for i in range(memory_map.USER_MD_MAX_LINES + 1))
    assert _codes(memory_map.lint_contract("user", long)) == ["over_cap"]
    assert _codes(memory_map.lint_contract("persona", "- PR #1")) == []


def test_page_budget(store):
    _page(store, "2_Wiki/Big.md", "x" * (memory_map.PAGE_BUDGET_BYTES + 1))
    _page(store, "2_Wiki/Small.md")
    findings = memory_map.lint_page_budgets(
        store.notebook_dir, store.list_notebook_pages()
    )
    assert [f.file for f in findings] == ["2_Wiki/Big.md"]


# --- store ---


@pytest.mark.asyncio
async def test_a_draft_never_overwrites_an_existing_file(store):
    store.memory_file_path.write_text("# My notes\n- by hand\n", encoding="utf-8")

    assert not await store.write_memory_map_if_missing("# Memory map\n")
    assert "by hand" in store.memory_file_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_the_map_is_written_whole(store):
    await store.write_memory_map("# Memory map\n\n- [[2_Wiki/]] — wiki\n\n\n")
    assert store.memory_file_path.read_text(encoding="utf-8") == (
        "# Memory map\n\n- [[2_Wiki/]] — wiki\n"
    )


@pytest.mark.asyncio
async def test_rejected_claims_round_trip(store):
    await store.append_rejected("The Perfect Drone", "2026-10-22")
    await store.append_rejected("the perfect  drone", "2026-10-23")

    assert store.read_rejected() == ["The Perfect Drone"]
    assert store.is_rejected("User wrote The Perfect Drone")
    assert not store.is_rejected("User wrote a novel")


@pytest.mark.asyncio
async def test_dream_ops_are_flushed_into_the_log(store):
    store.dream_ops_path.write_text(
        "- create 2_Wiki/Rust.md\n- retire a claim\n", encoding="utf-8"
    )

    assert await store.flush_dream_ops() == 2
    assert "- create 2_Wiki/Rust.md" in store.notebook_log_path.read_text("utf-8")
    assert store.dream_ops_path.read_text(encoding="utf-8") == ""
    assert await store.flush_dream_ops() == 0


@pytest.mark.asyncio
async def test_evidence_is_kept_in_the_log_but_not_indexed_as_a_fact(store):
    await store.append_daily_log(
        "chat-123",
        [
            {
                "content": "User prefers tea",
                "category": "preference",
                "tags": [],
                "evidence": "I always drink tea, never coffee",
            }
        ],
        date="2026-10-22",
    )
    text = await store.read_daily_log("2026-10-22")

    assert '  > "I always drink tea, never coffee"' in text
    facts = CoreMemoryFileIndexer._parse_archive_facts(text)
    assert [f["content"] for f in facts] == ["User prefers tea"]


def test_recalled_files_reads_the_source_file(store):
    store.append_recall("a snippet", "notebook", "3_Personal/Identity.md")
    store.append_recall("another", "archive_log", "")
    assert store.recalled_files() == {"3_Personal/Identity.md"}


# --- the agent has to be told ---


def test_prompt_describes_the_map():
    prompt = memory_context.format_core_memory_section({}, sandbox_enabled=True)

    assert "is a map" in prompt
    assert "memory:generated" not in prompt


# --- manager ---


def _manager(store):
    from suzent.memory.manager import MemoryManager

    mgr = MemoryManager.__new__(MemoryManager)
    mgr.markdown_store = store
    return mgr


@pytest.mark.asyncio
async def test_ensure_memory_map_drafts_only_when_missing(store):
    _page(store, "3_Personal/Identity.md")
    mgr = _manager(store)

    assert await mgr.ensure_memory_map()
    assert "[[3_Personal/]]" in store.memory_file_path.read_text("utf-8")
    assert not await mgr.ensure_memory_map()


@pytest.mark.asyncio
async def test_editing_the_facts_block_replaces_the_map(store):
    mgr = _manager(store)
    await store.write_memory_map("# Memory map\n\n- [[old]] — x\n")

    assert await mgr.update_memory_block("facts", "# Memory map\n\n- [[new]] — y\n")
    text = store.memory_file_path.read_text(encoding="utf-8")
    assert "[[new]]" in text and "[[old]]" not in text


@pytest.mark.asyncio
async def test_lint_memory_files_covers_every_injected_file(store):
    _page(store, "3_Personal/Identity.md")
    await store.write_block("user", "- PR #398 merged\n")
    mgr = _manager(store)

    codes = _codes(await mgr.lint_memory_files())

    assert "not_a_map" in codes
    assert "repo_state" in codes
