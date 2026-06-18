"""Tests for FTS5-backed chat search infra and the session_search tool."""

import asyncio
from types import SimpleNamespace

import pytest

from suzent.database.search import sanitize_messages
from suzent.tools.session_search_tool import SessionSearchTool, _parse_role_filter


@pytest.fixture
def db(temp_db):
    return temp_db


def _assistant(text, reasoning=None, tool=None):
    parts = []
    if reasoning:
        parts.append({"type": "reasoning", "text": reasoning})
    parts.append({"type": "text", "text": text})
    if tool:
        parts.append(
            {"type": "tool", "toolName": tool[0], "args": "{}", "output": tool[1]}
        )
    # `content` carries the legacy HTML form; search must ignore it.
    return {
        "role": "assistant",
        "content": f"<details>{reasoning}</details>{text}",
        "parts": parts,
    }


# --------------------------------------------------------------------------
# sanitize_messages: reads parts, drops reasoning, gates tool output
# --------------------------------------------------------------------------


def test_sanitize_drops_reasoning_and_tool_by_default():
    msgs = [
        {"role": "user", "content": "deploy the rocket"},
        _assistant(
            "press the button", reasoning="secret cot", tool=("read_file", "file body")
        ),
    ]
    out = sanitize_messages(msgs)
    joined = " ".join(m["text"] for m in out)
    assert "press the button" in joined
    assert "deploy the rocket" in joined
    assert "secret cot" not in joined  # reasoning never surfaced
    assert "file body" not in joined  # tool excluded by default
    assert "<details>" not in joined  # HTML content ignored


def test_sanitize_includes_tool_when_requested():
    msgs = [_assistant("answer", tool=("read_file", "TOOLBODY"))]
    out = sanitize_messages(msgs, role_filter=("user", "assistant", "tool"))
    joined = " ".join(m["text"] for m in out)
    assert "answer" in joined
    assert "TOOLBODY" in joined


# --------------------------------------------------------------------------
# reindex on write paths
# --------------------------------------------------------------------------


def test_create_chat_indexes_messages(db):
    db.create_chat("T", {}, [{"role": "user", "content": "alpha bravo charlie"}])
    assert db.fts_match_chat_ids("bravo")


def test_append_message_updates_index(db):
    cid = db.create_chat("T", {}, [{"role": "user", "content": "alpha"}])
    assert not db.fts_match_chat_ids("zulu")
    db.append_chat_message(cid, {"role": "user", "content": "zulu added later"})
    assert cid in (db.fts_match_chat_ids("zulu") or [])


def test_update_chat_replaces_index(db):
    cid = db.create_chat("T", {}, [{"role": "user", "content": "original word"}])
    db.update_chat(cid, messages=[{"role": "user", "content": "replaced text"}])
    assert not db.fts_match_chat_ids("original")
    assert cid in (db.fts_match_chat_ids("replaced") or [])


def test_delete_chat_removes_from_index(db):
    cid = db.create_chat("T", {}, [{"role": "user", "content": "deletme token"}])
    assert db.fts_match_chat_ids("deletme")
    db.delete_chat(cid)
    assert not db.fts_match_chat_ids("deletme")


# --------------------------------------------------------------------------
# Discovery / Read DB methods
# --------------------------------------------------------------------------


def test_discovery_returns_snippet_and_context(db):
    db.create_chat(
        "Rocket",
        {},
        [
            {"role": "user", "content": "how do I deploy the rocket"},
            _assistant("press the big red button"),
        ],
    )
    results = db.search_chat_messages("rocket", limit=3)
    assert len(results) == 1
    r = results[0]
    assert r["title"] == "Rocket"
    assert "rocket" in r["snippet"].lower()
    assert any("button" in m["text"] for m in r["context"])


def test_read_truncates_large_sessions(db):
    msgs = [{"role": "user", "content": f"msg number {i}"} for i in range(50)]
    cid = db.create_chat("Big", {}, msgs)
    out = db.read_chat_session(cid, head=20, tail=10)
    assert out["total_messages"] == 50
    assert out["truncated"] is True
    assert len(out["messages"]) == 30


def test_hidden_platform_excluded_from_discovery(db):
    db.create_chat(
        "Dreamy", {"platform": "dream"}, [{"role": "user", "content": "xyzzy"}]
    )
    assert db.search_chat_messages("xyzzy") == []


# --------------------------------------------------------------------------
# Chat-list search parity (LIKE fallback for short / CJK queries)
# --------------------------------------------------------------------------


def test_chat_list_search_uses_fts(db):
    db.create_chat(
        "Deploy notes", {}, [{"role": "user", "content": "deploy the service"}]
    )
    db.create_chat("Recipes", {}, [{"role": "user", "content": "pasta and sauce"}])
    titles = [c.title for c in db.list_chats(search="deploy")]
    assert "Deploy notes" in titles
    assert "Recipes" not in titles


def test_chat_list_short_cjk_falls_back_to_like(db):
    db.create_chat("CN", {}, [{"role": "user", "content": "部署火箭的方法"}])
    # 2-char CJK is below the trigram minimum → LIKE fallback must still match.
    assert db.fts_match_chat_ids("火箭") is None
    titles = [c.title for c in db.list_chats(search="火箭")]
    assert "CN" in titles


# --------------------------------------------------------------------------
# Codex review fixes
# --------------------------------------------------------------------------


def test_legacy_assistant_without_parts_never_leaks_content():
    """An assistant row with no `parts` (legacy HTML in `content`) must yield no text,
    not the raw reasoning/HTML markup."""
    msgs = [
        {"role": "user", "content": "a question"},
        {
            "role": "assistant",
            "content": '<details data-reasoning="true">secret cot</details>visible?',
        },
    ]
    out = sanitize_messages(msgs)
    joined = " ".join(m["text"] for m in out)
    assert "secret cot" not in joined
    assert "<details" not in joined
    # Only the user message survives.
    assert [m["role"] for m in out] == ["user"]


def test_discovery_falls_back_to_like_for_short_query(db):
    # 2-char CJK is below the trigram minimum; Discovery must still find it via LIKE.
    db.create_chat("CN", {}, [{"role": "user", "content": "部署火箭的方法"}])
    assert db.fts_match_chat_ids("火箭") is None
    results = db.search_chat_messages("火箭")
    assert [r["title"] for r in results] == ["CN"]


def test_discovery_excludes_chat_before_limit(db):
    # Two chats match; with limit=1 and the higher-ranked one excluded, the other
    # must still be returned (exclusion must not consume the single slot).
    a = db.create_chat("A", {}, [{"role": "user", "content": "keyword apple"}])
    db.create_chat("B", {}, [{"role": "user", "content": "keyword apple"}])
    results = db.search_chat_messages("apple", limit=1, exclude_chat_id=a)
    assert len(results) == 1
    assert results[0]["chat_id"] != a


def test_backfill_resumes_for_unindexed_chats(db):
    # Simulate an interrupted backfill: a chat exists but has no FTS rows.
    cid = db.create_chat("Resume", {}, [{"role": "user", "content": "resumeword"}])
    db.remove_chat_from_fts(cid)
    assert not db.fts_match_chat_ids("resumeword")
    # Re-running init must index the missing chat rather than skipping because the
    # index is already non-empty (other chats present).
    db.create_chat("Other", {}, [{"role": "user", "content": "otherword"}])
    db._init_chat_search()
    assert cid in (db.fts_match_chat_ids("resumeword") or [])


# --------------------------------------------------------------------------
# session_search tool: mode dispatch
# --------------------------------------------------------------------------


def _ctx(db, chat_id=""):
    # The tool reads only ctx.deps.chat_id; get_database() returns the shared singleton,
    # so point it at the temp db for the duration of the test.
    return SimpleNamespace(deps=SimpleNamespace(chat_id=chat_id))


@pytest.fixture
def tool_db(db, monkeypatch):
    monkeypatch.setattr("suzent.tools.session_search_tool.get_database", lambda: db)
    return db


def test_role_filter_parsing():
    assert _parse_role_filter("user,assistant") == ("user", "assistant")
    assert _parse_role_filter("tool") == ("tool",)
    assert _parse_role_filter("garbage") == ("user", "assistant")
    assert _parse_role_filter("user,assistant,tool") == ("user", "assistant", "tool")


def test_tool_read_mode(tool_db):
    cid = tool_db.create_chat(
        "Sess",
        {},
        [
            {"role": "user", "content": "hello there"},
            _assistant("general kenobi", reasoning="hidden"),
        ],
    )
    tool = SessionSearchTool()
    res = asyncio.run(tool.forward(_ctx(tool_db), session_id=cid))
    assert res.success
    assert "general kenobi" in res.message
    assert "hidden" not in res.message
    assert res.metadata["mode"] == "read"


def test_tool_discovery_excludes_current_chat(tool_db):
    a = tool_db.create_chat(
        "A", {}, [{"role": "user", "content": "shared keyword apple"}]
    )
    b = tool_db.create_chat(
        "B", {}, [{"role": "user", "content": "shared keyword apple"}]
    )
    tool = SessionSearchTool()
    # Searching from chat A should not return A itself.
    res = asyncio.run(tool.forward(_ctx(tool_db, chat_id=a), query="apple"))
    assert res.success
    assert "session_id: %s" % b in res.message
    assert "session_id: %s" % a not in res.message


def test_tool_browse_mode(tool_db):
    tool_db.create_chat("One", {}, [{"role": "user", "content": "first"}])
    tool_db.create_chat("Two", {}, [{"role": "user", "content": "second"}])
    tool = SessionSearchTool()
    res = asyncio.run(tool.forward(_ctx(tool_db)))
    assert res.success
    assert res.metadata["mode"] == "browse"
    assert "One" in res.message or "Two" in res.message


def test_browse_counts_visible_messages_not_stale_sidebar_count(tool_db):
    """Browse must recompute the visible message count, not trust the (assistant-only,
    possibly stale) sidebar summary. A user msg + a text reply = 2 visible messages."""
    cid = tool_db.create_chat(
        "Convo",
        {},
        [
            {"role": "user", "content": "question here"},
            _assistant("the answer"),
        ],
    )
    # Force the sidebar summary count stale (as happens for chats summarized before
    # their assistant reply landed).
    tool_db.merge_chat_config(cid, {"_summary_visible_assistant_count": 0})
    res = asyncio.run(SessionSearchTool().forward(_ctx(tool_db)))
    assert "0 messages" not in res.message
    assert "2 messages" in res.message
