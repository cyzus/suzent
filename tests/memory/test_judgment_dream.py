"""The dream judges typed candidates: it routes by tag, sees what the user rejected and
what is still open, records its operations for log.md, and only wakes when there is
something to judge."""

import pytest

from suzent.config import CONFIG
from suzent.core import dream_runner as dr_mod
from suzent.core.dream_runner import DreamRunner
from suzent.memory import memory_context
from suzent.memory.indexer import CoreMemoryFileIndexer
from suzent.memory.markdown_store import MarkdownMemoryStore

ROOTS = memory_context.resolve_dream_roots(sandbox_enabled=True)


def _brief(**queues) -> str:
    return memory_context.build_dream_instructions(
        ROOTS,
        start="2026-10-14",
        end="2026-10-22",
        confirmations="   (none pending)",
        revisits="   (none due)",
        **queues,
    )


# --- prompts ---


def test_candidates_are_routed_by_kind():
    text = _brief()

    for tag, home in (
        ("`kind:user`", "a `type: personal` page"),
        ("`kind:experience`", "a `type: experience` page"),
        ("`kind:world`", "a knowledge page"),
    ):
        assert f"{tag} -> {home}" in text
    assert "Never on a personal page" in text
    assert "`ungrounded`" in text


def test_the_briefs_name_no_vault_folders():
    """Users rename and renumber folders; placement follows their schema, not the brief."""
    for text in (_brief(), memory_context.build_lint_instructions(ROOTS)):
        for folder in ("0_Inbox", "1_Projects", "2_Wiki", "3_Personal", "4_Experience"):
            assert folder not in text


@pytest.mark.parametrize(
    "build",
    [memory_context.build_dream_system_prompt, memory_context.build_lint_system_prompt],
)
def test_placement_comes_from_the_notebook_skill(build):
    """The dream loads no skills, so the skill's filing reference is inlined. It must
    leave schema.md to the user rather than have the dream record placement there."""
    system = build(ROOTS)

    assert "# Filing memory pages" in system
    assert "Never create a new numbered top-level folder" in system
    assert "never edit it" in system


def test_the_brief_carries_rejected_claims_open_questions_and_findings():
    text = _brief(
        rejected=memory_context.format_lines_block(["Wrote The Perfect Drone"]),
        questions=memory_context.format_lines_block(["Is it Zurich or Basel?"]),
        findings=memory_context.format_lines_block(["[not_a_map] MEMORY.md: line 3"]),
    )

    assert "   - Wrote The Perfect Drone" in text
    assert "   - Is it Zurich or Basel?" in text
    assert "   - [not_a_map] MEMORY.md: line 3" in text
    assert "Do not ask them again" in text


def test_the_agent_records_operations_outside_log_md():
    system = memory_context.build_dream_system_prompt(ROOTS)

    assert ROOTS.dream_ops_path.endswith("/.state/dream_ops.md")
    assert f"Record every operation in {ROOTS.dream_ops_path}" in system
    assert "`- skip <candidate>: <reason>`" in system
    assert 'Never append\n  "(previously ...)"' in system


def test_the_lint_brief_carries_findings():
    text = memory_context.build_lint_instructions(
        ROOTS, findings=memory_context.format_lines_block(["[too_big] 2_Wiki/A.md"])
    )

    assert "   - [too_big] 2_Wiki/A.md" in text


def test_an_empty_list_renders_as_none():
    assert memory_context.format_lines_block([]) == "   (none)"
    assert memory_context.format_lines_block(["  a\n b "]) == "   - a b"


# --- core prompt ---


def test_open_questions_reach_the_conversation_capped():
    questions = [f"Question {i}?" for i in range(8)]
    text = memory_context.format_core_memory_section({}, open_questions=questions)

    assert "## Open memory questions" in text
    assert "- Question 4?" in text
    assert "Question 5?" not in text
    assert "`memory_update`" in text


def test_no_questions_no_section():
    assert "Open memory questions" not in memory_context.format_core_memory_section({})


def test_answering_a_question_invalidates_the_cached_prompt(tmp_path):
    store = MarkdownMemoryStore(
        base_dir=tmp_path / "memory", notebook_dir=str(tmp_path / "notebook")
    )
    before = store.core_memory_revision()
    store.review_queue_path.parent.mkdir(parents=True, exist_ok=True)
    store.review_queue_path.write_text("- Zurich or Basel?\n", encoding="utf-8")

    assert store.core_memory_revision() != before


# --- ranking ---


def test_the_frontmatter_count_ranks_like_the_inline_marker():
    strength = CoreMemoryFileIndexer._claim_strength
    page = "---\ntype: personal\nconfirmed: 3\n---\n- Likes tea\n"
    lifecycle = CoreMemoryFileIndexer._parse_page_lifecycle(page)

    assert lifecycle["confirmed"] == "3"
    assert strength("- Likes tea", lifecycle) == strength(
        "- Likes tea (confirmed 3x, last 2026-10-01)", {}
    )
    assert strength("- Likes tea (confirmed 6x)", lifecycle) > strength(
        "- Likes tea", lifecycle
    )


# --- runner ---


class _Store:
    def __init__(self, facts: int):
        self.facts = facts
        self.flushed = 0

    def read_watermark(self):
        return "2026-10-13"

    async def flush_dream_ops(self):
        self.flushed += 1
        return 3


class _Mgr:
    def __init__(self, facts: int):
        self.markdown_store = _Store(facts)
        self.llm_client = object()


def _runner(monkeypatch, mgr, *, last_attempt_hours_ago: float, failures=None):
    monkeypatch.setattr(CONFIG, "memory_consolidation_enabled", True)
    monkeypatch.setattr(CONFIG, "memory_consolidation_min_facts", 20)
    monkeypatch.setattr(CONFIG, "memory_consolidation_min_hours", 24)
    monkeypatch.setattr(CONFIG, "memory_consolidation_max_days", 7)
    monkeypatch.setattr(dr_mod, "get_memory_manager", lambda: mgr)
    r = DreamRunner()
    r._failures_loaded = True
    r._failures = failures or {}
    r._last_attempt_at = dr_mod.time.time() - last_attempt_hours_ago * 3600
    monkeypatch.setattr(r, "_pending_dates", lambda m, wm: ["2026-10-21", "2026-10-22"])
    monkeypatch.setattr(r, "_count_fact_lines", lambda m, d: m.markdown_store.facts)
    monkeypatch.setattr(r, "_queues_due", lambda m: False)
    monkeypatch.setattr(r, "_lint_due", lambda m: False)
    calls = {"dream": 0, "advanced": []}

    async def _dream(m, wm, pending):
        calls["dream"] += 1

    async def _advance(m, w_new):
        calls["advanced"].append(w_new)

    monkeypatch.setattr(r, "_run_dream", _dream)
    monkeypatch.setattr(r, "_advance_watermark", _advance)
    return r, calls


async def test_logs_without_candidates_advance_without_a_model_call(monkeypatch):
    r, calls = _runner(monkeypatch, _Mgr(facts=0), last_attempt_hours_ago=48)

    await r._tick()

    assert calls == {"dream": 0, "advanced": ["2026-10-22"]}


@pytest.mark.parametrize(
    ("facts", "hours", "failures", "runs"),
    [
        (25, 1, None, True),
        (5, 1, None, False),
        (5, 30, None, True),
        (25, 1, {"2026-10-22": 1}, False),
    ],
    ids=["enough", "too-few-too-soon", "daily", "failed-batch-waits"],
)
async def test_the_dream_runs_on_volume_or_once_a_day(
    monkeypatch, facts, hours, failures, runs
):
    r, calls = _runner(
        monkeypatch, _Mgr(facts=facts), last_attempt_hours_ago=hours, failures=failures
    )

    await r._tick()

    assert calls["dream"] == int(runs)
    assert calls["advanced"] == []


async def test_the_op_log_is_moved_to_log_md():
    mgr = _Mgr(facts=0)

    await DreamRunner._flush_dream_ops(mgr)

    assert mgr.markdown_store.flushed == 1
