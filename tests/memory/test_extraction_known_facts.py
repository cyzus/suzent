"""Extraction must see what memory already holds.

Blind per-turn extraction is the source of most archival duplication: a stable fact
(a name, a long-running project, how someone likes to be addressed) is re-extracted
every time it comes up. Showing the model the nearest known facts is what lets it
tell a re-mention from an update — without dropping updates, which is what the
removed write-time similarity threshold got wrong (#34).
"""

import pytest

from suzent.memory import memory_context
from suzent.memory.manager import KNOWN_FACTS_LIMIT, MemoryManager


class _StubManager:
    """Exercises _recall_known_facts without standing up the whole manager."""

    _recall_known_facts = MemoryManager._recall_known_facts

    def __init__(self, results=None, error=None):
        self._results = results or []
        self._error = error
        self.calls = []

    async def search_memories(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._results


# --- prompt shape ---


def test_known_facts_absent_leaves_the_prompt_unchanged():
    """No retrieval, no behaviour change — the old prompt exactly."""
    assert memory_context.format_known_facts_block([]) == ""
    assert memory_context.format_known_facts_block(None) == ""

    bare = memory_context.format_fact_extraction_user_prompt("a turn")

    assert "Already in memory" not in bare
    assert "a turn" in bare


def test_known_facts_are_rendered_and_labelled():
    prompt = memory_context.format_fact_extraction_user_prompt(
        "a turn", ["Prefers dark mode", "Building a VR horror game"]
    )

    assert "## Already in memory" in prompt
    assert "- Prefers dark mode" in prompt
    assert "- Building a VR horror game" in prompt
    assert "a turn" in prompt


def test_system_prompt_permits_updates():
    """The rule must not read as a blanket 'skip anything similar'."""
    rules = memory_context.FACT_EXTRACTION_SYSTEM_PROMPT

    assert "Already-known facts" in rules
    assert "CHANGES" in rules
    assert "worse than storing a duplicate" in rules


# --- recall ---


@pytest.mark.asyncio
async def test_recall_returns_contents_nearest_first():
    mgr = _StubManager(
        [{"content": "Prefers dark mode"}, {"content": "Uses Unreal Engine 5"}]
    )

    facts = await mgr._recall_known_facts("some turn", "user-1", "chat-1")

    assert facts == ["Prefers dark mode", "Uses Unreal Engine 5"]
    assert mgr.calls[0]["limit"] == KNOWN_FACTS_LIMIT
    assert mgr.calls[0]["user_id"] == "user-1"


@pytest.mark.asyncio
async def test_recall_dedupes_and_normalises_whitespace():
    mgr = _StubManager(
        [
            {"content": "Prefers   dark\nmode"},
            {"content": "prefers dark mode"},
            {"content": ""},
        ]
    )

    facts = await mgr._recall_known_facts("some turn", "user-1")

    assert facts == ["Prefers dark mode"]


@pytest.mark.asyncio
async def test_recall_failure_never_blocks_extraction():
    """Enriching the prompt is best-effort; a search outage must not lose facts."""
    mgr = _StubManager(error=RuntimeError("lancedb down"))

    assert await mgr._recall_known_facts("some turn", "user-1") == []


@pytest.mark.asyncio
async def test_blank_turn_skips_the_search_entirely():
    mgr = _StubManager([{"content": "Prefers dark mode"}])

    assert await mgr._recall_known_facts("   \n  ", "user-1") == []
    assert mgr.calls == []
