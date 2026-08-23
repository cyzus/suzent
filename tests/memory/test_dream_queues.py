"""The two queues the runner hands the dream: confirmations, and claims to revisit.

Both are deterministic scans the runner owns. Asking the agent to find expired pages
by reading the whole vault, or to discover confirmations by re-reading logs that were
deliberately not written, would be slower and less reliable than reading the files.
"""

import pytest

from suzent.core.dream_runner import DreamRunner
from suzent.memory import memory_context
from suzent.memory.markdown_store import MarkdownMemoryStore


class _Mgr:
    def __init__(self, store):
        self.markdown_store = store


def _page(store, rel: str, body: str):
    path = store.notebook_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def store(tmp_path):
    return MarkdownMemoryStore(
        base_dir=tmp_path, notebook_dir=str(tmp_path / "notebook")
    )


# --- revisit queue ---


def test_only_expired_pages_are_queued_soonest_first(store):
    _page(store, "3_Personal/a.md", "---\nstale_after: 2020-01-01\n---\n- old")
    _page(store, "3_Personal/b.md", "---\nstale_after: 2019-01-01\n---\n- older")
    _page(store, "3_Personal/c.md", "---\nstale_after: 2099-01-01\n---\n- fresh")
    _page(store, "3_Personal/d.md", "- no frontmatter at all")

    rows = DreamRunner._due_revisits(_Mgr(store))

    assert [r["page"] for r in rows] == ["3_Personal/b.md", "3_Personal/a.md"]


def test_a_deprecated_page_is_not_worth_revisiting(store):
    _page(
        store,
        "3_Personal/a.md",
        "---\nstatus: deprecated\nstale_after: 2020-01-01\n---\n- old",
    )

    assert DreamRunner._due_revisits(_Mgr(store)) == []


def test_the_queue_is_bounded(store):
    for i in range(30):
        _page(
            store, f"3_Personal/p{i:02d}.md", "---\nstale_after: 2020-01-01\n---\n- x"
        )

    assert len(DreamRunner._due_revisits(_Mgr(store), limit=5)) == 5


def test_an_unreadable_vault_yields_an_empty_queue():
    class _Broken:
        @property
        def markdown_store(self):
            raise RuntimeError("no vault")

    assert DreamRunner._due_revisits(_Broken()) == []


# --- prompt rendering ---


def test_the_instructions_carry_both_queues_and_never_delete():
    text = memory_context.DREAM_INSTRUCTIONS.format(
        start="2026-01-01",
        end="2026-01-02",
        confirmations=memory_context.format_confirmations_block(
            [{"content": "likes tea", "count": 3, "last": "2026-01-02"}]
        ),
        revisits=memory_context.format_revisits_block(
            [{"page": "3_Personal/a.md", "stale_after": "2020-01-01"}]
        ),
    )

    assert "likes tea — +3x, last 2026-01-02" in text
    assert "3_Personal/a.md (stale_after 2020-01-01)" in text
    assert "Never delete here." in text
    # A restatement that contradicts the page is a correction and never reaches the
    # confirmations list; the prompt has to say so or the agent may bump the marker.
    assert "a contradicting restatement never reaches this list" in text


def test_empty_queues_render_as_explicit_nothing():
    assert memory_context.format_confirmations_block([]) == "   (none pending)"
    assert memory_context.format_confirmations_block(None) == "   (none pending)"
    assert memory_context.format_revisits_block([]) == "   (none due)"
