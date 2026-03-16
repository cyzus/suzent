from suzent.core.stream_registry import (
    merge_pending_auto_approvals,
    pending_auto_approvals,
    pop_pending_auto_approvals,
)


def teardown_function():
    pending_auto_approvals.clear()


def test_merge_and_pop_pending_auto_approvals():
    chat_id = "chat-1"

    merge_pending_auto_approvals(chat_id, {"a": True})
    merge_pending_auto_approvals(chat_id, {"b": False})
    merge_pending_auto_approvals(chat_id, {"a": False})

    merged = pop_pending_auto_approvals(chat_id)
    assert merged == {"a": False, "b": False}
    assert pop_pending_auto_approvals(chat_id) == {}


def test_merge_pending_auto_approvals_ignores_empty_inputs():
    merge_pending_auto_approvals("", {"a": True})
    merge_pending_auto_approvals("chat-2", {})
    assert pending_auto_approvals == {}
