from unittest.mock import patch

from suzent.core.chat_processor import _resolve_resume_approval_actions
from suzent.database.chats import _summarize_messages
from suzent.permissions.actions import build_approval_decision


def test_config_save_preserves_pending_approval_for_resume(temp_db) -> None:
    chat = temp_db.create_chat(
        title="Approval test", config={"permission_mode": "auto"}
    )
    decision = build_approval_decision(
        "edit_image", {}, reason="Needs approval", reason_code="test"
    ).model_dump(mode="json", by_alias=True)
    pending = [
        {
            "approvalId": "call-edit",
            "toolCallId": "call-edit",
            "toolName": "edit_image",
            "args": {},
            "decision": decision,
        }
    ]
    temp_db.merge_chat_config(chat, {"_pending_approvals": pending})
    temp_db.update_chat(chat, config={"permission_mode": "auto"}, messages=[])
    with patch("suzent.core.chat_processor.get_database", return_value=temp_db):
        resolved = _resolve_resume_approval_actions(
            chat, [{"request_id": "call-edit", "action_id": "allow_once"}]
        )
    assert len(resolved) == 1
    assert resolved[0]["approved"] is True
    assert resolved[0]["tool_call_id"] == "call-edit"
    assert resolved[0]["remember"] == ""


def test_stale_config_cannot_restore_resolved_approval(temp_db) -> None:
    chat = temp_db.create_chat(title="Approval test", config={})
    stale = {"_pending_approvals": [{"approvalId": "old-call"}]}
    temp_db.merge_chat_config(chat, {"_pending_approvals": []})
    temp_db.update_chat(chat, config=stale)
    assert temp_db.get_chat(chat).config["_pending_approvals"] == []


def test_draft_write_cannot_wipe_a_concurrently_saved_approval(
    temp_db, monkeypatch
) -> None:
    """A messages write that read the config before an approval was saved keeps it.

    The streaming draft runs in a background thread. When it had read the config
    just before the pending approval landed and then wrote the whole dict back,
    the approval vanished and the user's decision on it was rejected as stale.
    """
    import threading

    import suzent.database.chats as chats_module

    chat = temp_db.create_chat(title="Race", config={"permission_mode": "default"})
    summarizing, release = threading.Event(), threading.Event()
    summarize = chats_module._message_summary

    def paused_summary(messages):
        summarizing.set()
        release.wait(5)
        return summarize(messages)

    monkeypatch.setattr(chats_module, "_message_summary", paused_summary)
    draft = threading.Thread(
        target=temp_db.update_chat,
        args=(chat,),
        kwargs={
            "messages": [{"role": "assistant", "content": "draft"}],
            "reindex": False,
        },
    )
    draft.start()
    assert summarizing.wait(5)
    monkeypatch.setattr(chats_module, "_message_summary", summarize)

    temp_db.merge_chat_config(chat, {"_pending_approvals": [{"approvalId": "call-1"}]})
    release.set()
    draft.join(5)

    config = temp_db.get_chat(chat).config
    assert config["_pending_approvals"] == [{"approvalId": "call-1"}]
    assert config["permission_mode"] == "default"
    assert config["_summary_last_message"] == "draft"


def test_merge_chat_config_only_touches_the_given_keys(temp_db) -> None:
    chat = temp_db.create_chat(title="Merge", config={"model": "m", "tools": ["a"]})
    temp_db.merge_chat_config(
        chat, {"title_hint": "日本語", "nested": {"a": [1, None]}}
    )
    temp_db.merge_chat_config(chat, {"model": None})

    config = temp_db.get_chat(chat).config
    assert config["model"] is None
    assert config["tools"] == ["a"]
    assert config["title_hint"] == "日本語"
    assert config["nested"] == {"a": [1, None]}


def test_config_replace_keeps_summary_and_drops_absent_keys(temp_db) -> None:
    chat = temp_db.create_chat(
        title="Replace",
        config={"model": "m", "stale": True},
        messages=[{"role": "assistant", "content": "hello"}],
    )
    temp_db.update_chat(chat, config={"model": "n"})

    config = temp_db.get_chat(chat).config
    assert config["model"] == "n"
    assert "stale" not in config
    assert "_pending_approvals" not in config
    assert config["_summary_last_message"] == "hello"
    assert config["_summary_visible_assistant_count"] == 1


def test_unread_count_survives_and_increments(temp_db) -> None:
    chat = temp_db.create_chat(title="Unread", config={"unread_count": 2})
    revision = temp_db.commit_snapshot_state(chat, b"{}")
    assert temp_db.finalize_state_if_revision_matches(chat, revision, b"{}")
    assert temp_db.get_chat(chat).config["unread_count"] == 3

    temp_db.mark_chat_read(chat)
    assert temp_db.get_chat(chat).config["unread_count"] == 0


def test_sidebar_summary_skips_tool_output() -> None:
    messages = [
        {"role": "user", "content": "start the work"},
        {"role": "assistant", "content": "checking the code"},
        {"role": "tool", "content": '{"message": "private tool output"}'},
    ]

    assert _summarize_messages(messages) == (1, "checking the code")
