from unittest.mock import patch

from suzent.core.chat_mentions import build_chat_mention_context


def test_references_are_metadata_only_without_database_access() -> None:
    with patch("suzent.database.get_database") as get_db:
        context = build_chat_mention_context(
            "@[chat://abc/%E8%AE%BE%E8%AE%A1] @[chat://abc/duplicate] @[/workspace/test.py]"
        )
    get_db.assert_not_called()
    assert context.count('"id": "abc"') == 1
    assert '"title": "设计"' in context
    assert "session_search(session_id=<id>, offset=0" in context
    assert "Read a referenced chat before relying" in context
    assert "/workspace" not in context


def test_external_agent_uses_on_demand_cli_reader() -> None:
    context = build_chat_mention_context("@[chat://abc/title]", external_agent=True)
    assert "suzent chats read <id>" in context
    assert "session_search" not in context
    assert "not conversation contents" in context


def test_file_mentions_do_not_add_chat_context() -> None:
    assert build_chat_mention_context("@[/workspace/test.py]") == ""


def test_reference_titles_are_json_escaped() -> None:
    context = build_chat_mention_context("@[chat://abc/title%0A%22fake%22]")
    assert '"title": "title\\n\\"fake\\""' in context
    assert "untrusted context" in context
