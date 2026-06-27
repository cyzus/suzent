"""Unit tests for CitationManager — the single authority for source IDs."""

from suzent.core.citation_manager import CitationManager, CitationSourceType


def test_register_assigns_sequential_ids():
    mgr = CitationManager()
    a = mgr.register(CitationSourceType.WEB_SEARCH, "A", url="https://a.com")
    b = mgr.register(CitationSourceType.WEB_SEARCH, "B", url="https://b.com")
    assert a == "t0_src_1"
    assert b == "t0_src_2"
    assert [s.id for s in mgr.get_all()] == ["t0_src_1", "t0_src_2"]


def test_turn_prefix_makes_ids_unique_across_turns():
    t0 = CitationManager(turn=0)
    t3 = CitationManager(turn=3)
    assert (
        t0.register(CitationSourceType.WEB_SEARCH, "A", url="https://a.com")
        == "t0_src_1"
    )
    assert (
        t3.register(CitationSourceType.WEB_SEARCH, "B", url="https://b.com")
        == "t3_src_1"
    )


def test_register_dedups_same_url():
    mgr = CitationManager()
    first = mgr.register(CitationSourceType.WEBPAGE, "Page", url="https://x.com")
    again = mgr.register(
        CitationSourceType.WEBPAGE, "Page (again)", url="https://x.com"
    )
    assert first == again
    assert len(mgr.get_all()) == 1


def test_dedup_is_per_type():
    mgr = CitationManager()
    s = mgr.register(CitationSourceType.WEB_SEARCH, "X", url="https://x.com")
    w = mgr.register(CitationSourceType.WEBPAGE, "X", url="https://x.com")
    assert s != w
    assert len(mgr.get_all()) == 2


def test_snippet_truncated_to_200():
    mgr = CitationManager()
    sid = mgr.register(CitationSourceType.FILE, "f", snippet="z" * 500)
    assert len(mgr.get(sid).snippet) == 200


def test_prompt_context_lists_ids_and_titles():
    mgr = CitationManager()
    mgr.register(
        CitationSourceType.WEB_SEARCH, "Reuters", url="https://r.com", snippet="hot"
    )
    ctx = mgr.to_prompt_context()
    assert "[t0_src_1]" in ctx
    assert "Reuters" in ctx
    assert "https://r.com" in ctx


def test_empty_prompt_context_is_blank():
    assert CitationManager().to_prompt_context() == ""


def test_event_payload_shape():
    mgr = CitationManager()
    mgr.register(
        CitationSourceType.WEB_SEARCH,
        "Reuters",
        url="https://r.com",
        favicon="https://r.com/fav.ico",
    )
    payload = mgr.to_event_payload()
    assert payload == [
        {
            "id": "t0_src_1",
            "type": "search",
            "title": "Reuters",
            "url": "https://r.com",
            "snippet": None,
            "favicon": "https://r.com/fav.ico",
        }
    ]


def test_clear_resets_counter_and_sources():
    mgr = CitationManager()
    mgr.register(CitationSourceType.FILE, "f", url="file:///a")
    mgr.clear()
    assert mgr.get_all() == []
    assert mgr.register(CitationSourceType.FILE, "g", url="file:///b") == "t0_src_1"
