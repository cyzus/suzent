import asyncio

from suzent.core.stream_registry import (
    background_queues,
    merge_pending_auto_approvals,
    pending_auto_approvals,
    pop_pending_auto_approvals,
    register_background_stream,
    try_register_background_stream,
    unregister_background_stream,
)


def teardown_function():
    pending_auto_approvals.clear()
    background_queues.clear()


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


def test_try_register_background_stream_rejects_active_producer():
    chat_id = "chat-3"

    first = try_register_background_stream(chat_id)
    second = try_register_background_stream(chat_id)

    assert first is not None
    assert second is None
    assert background_queues[chat_id] is first


def test_register_background_stream_can_replace_finished_queue():
    chat_id = "chat-4"
    first = register_background_stream(chat_id)
    asyncio.run(first.put(None))

    second = try_register_background_stream(chat_id)

    assert second is not None
    assert second is not first
    assert background_queues[chat_id] is second


def test_background_stream_queue_does_not_block_without_live_consumer():
    queue = register_background_stream("chat-5")

    async def fill_queue() -> None:
        for index in range(2500):
            await queue.put(f"data: {index}\n\n")

    asyncio.run(fill_queue())

    assert queue.qsize() == 2500


def test_unregister_background_stream_keeps_newer_queue():
    chat_id = "chat-6"
    old_queue = register_background_stream(chat_id)
    old_queue.producer_active = False
    new_queue = register_background_stream(chat_id)

    unregister_background_stream(chat_id, old_queue)

    assert background_queues[chat_id] is new_queue
