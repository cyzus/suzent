"""The one-time cleanup writes drafts for the user to review and changes nothing live."""

import json

import pytest

from suzent.memory import cleanup, memory_map
from suzent.memory.markdown_store import MarkdownMemoryStore

LEGACY = """# Long-term Memory
<!-- memory:generated -->
- [[3_Personal/Profile]] User is a PhD student
- Prefers dark mode
<!-- /memory:generated -->

*Last updated: 2026-10-01 UTC*
"""
USER_MD = """# User
- Name: Sam
- Every morning at 9:00 send the news report
- PR #398 merged
- Wrote The Perfect Drone
"""
PROFILE = """---
type: personal
---
# Profile
- Name: Sam
- PhD in robotics at ETH
"""


@pytest.fixture
def store(tmp_path):
    return MarkdownMemoryStore(
        base_dir=tmp_path / "memory", notebook_dir=str(tmp_path / "notebook")
    )


def _page(store, rel: str, body: str) -> None:
    path = store.notebook_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


@pytest.fixture
async def drafted(store):
    store.memory_file_path.write_text(LEGACY, encoding="utf-8")
    await store.write_block("user", USER_MD)
    _page(store, "3_Personal/Profile.md", PROFILE + "- Commit abc1234def merged\n")
    _page(store, "2_Wiki/Rust.md", "# Rust\nOwnership rules.\n")
    _page(store, "2_Wiki/Acp.md", "---\ntype: concept\n---\n# ACP\nv1.2.3 signs in.\n")
    result = await cleanup.write_cleanup_drafts(store, date="2026-10-22")
    return result, {p.name: p.read_text(encoding="utf-8") for p in result.files}


async def test_nothing_live_changes(store, drafted):
    result, _ = drafted

    assert store.memory_file_path.read_text(encoding="utf-8") == LEGACY
    assert await store.read_block("user") == USER_MD
    assert store.read_rejected() == []
    assert result.out_dir == store.notebook_state_dir / "cleanup" / "2026-10-22"


async def test_the_map_draft_replaces_an_old_summary(store, drafted):
    _, files = drafted
    draft = files["MEMORY.draft.md"]

    assert draft.startswith(memory_map.MAP_HEADING)
    assert "[[3_Personal/Profile]]" in draft and "[[2_Wiki/]]" in draft
    assert "Prefers dark mode" not in draft
    assert (
        "### From MEMORY.md\n- [[3_Personal/Profile]] User is a PhD student\n- Prefers dark mode"
        in files["rewrite_brief.md"]
    )


async def test_user_md_keeps_only_its_contract(drafted):
    _, files = drafted

    assert files["user.draft.md"] == "# User\n- Name: Sam\n"
    brief = files["rewrite_brief.md"]
    assert "- Every morning at 9:00 send the news report" in brief
    assert "- PR #398 merged" in brief
    assert "- Wrote The Perfect Drone" in brief


async def test_profile_loses_what_user_md_owns(drafted):
    _, files = drafted

    assert "Name: Sam" not in files["Profile.md"]
    assert "PhD in robotics" in files["Profile.md"]
    assert "-- Name: Sam" in files["migration.diff"]


async def test_the_brief_flags_pages(drafted):
    _, files = drafted
    brief = files["rewrite_brief.md"]

    assert "### 3_Personal/Profile.md\n- line 7 looks like repo_state" in brief
    # A version on a knowledge page is a citation, not repo state.
    assert "### 2_Wiki/Rust.md\n- no `type:` in frontmatter" in brief
    assert "2_Wiki/Acp.md" not in brief


async def test_known_wrong_claims_are_seeded_once(store, drafted):
    _, files = drafted
    seeds = [json.loads(ln) for ln in files["rejected.seed.jsonl"].splitlines()]
    assert [s["content"] for s in seeds] == ["The Perfect Drone"]

    await store.append_rejected("The Perfect Drone", "2026-10-22")
    again = await cleanup.write_cleanup_drafts(store, date="2026-10-23")
    assert (again.out_dir / "rejected.seed.jsonl").read_text(encoding="utf-8") == ""


async def test_the_readme_carries_the_lint(drafted):
    _, files = drafted
    assert "[not_a_map] MEMORY.md" in files["README.md"]


def test_an_existing_map_keeps_the_users_lines(store):
    _page(store, "3_Personal/Identity.md", "# Identity\n")
    _page(store, "3_Personal/Health.md", "---\ntype: personal\n---\n# Health\n")
    current = (
        "# Memory map\n\n"
        "- [[3_Personal/Identity]] — who I am; my own words\n"
        "- likes tea\n"
    )

    draft, moved = cleanup.draft_memory_map(
        current, store.notebook_dir, store.list_notebook_pages()
    )

    assert "- [[3_Personal/Identity]] — who I am; my own words" in draft
    assert "[[3_Personal/Health]]" in draft
    assert "likes tea" not in draft
    assert moved == ["- likes tea"]


def test_cli_uses_the_mapped_vault(tmp_path, monkeypatch):
    from suzent.cli import memory as memory_cli
    from suzent.config import CONFIG

    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(CONFIG, "sandbox_data_path", str(tmp_path / "data"))
    monkeypatch.setattr(CONFIG, "sandbox_volumes", [f"{vault}:/mnt/notebook"])

    assert memory_cli._store().notebook_dir == vault.resolve()
